/* tos.ld — link TOSTEST.PRG and TOSBENCH.PRG at base 0 as one contiguous text+data blob (GEMDOS
 * relocates it at load). rodata folds into text so it is reachable; .bss is zeroed by TOS. Packed
 * tight (no gaps) so a fixup's virtual address equals its byte offset in the flat binary, which is
 * what lets mkprg.py build the relocation table straight out of the ELF's own fixups.
 *
 * THIS IS NOT tos_rom.ld, which links the rebuilt ROM at its burned-in 0xFC0000 and asserts that it
 * carries no .bss and no .data at all. These two programs are ordinary GEMDOS applications and have
 * both.
 *
 * GEMDOS places BSS immediately after text+data (at tlen+dlen), so .bss MUST start there with no
 * gap. A BSS symbol with a large alignment would otherwise push .bss past the end of the emitted
 * binary, and every BSS access on-target would land at the wrong address (the classic "handle 0 /
 * silent corruption" bug). We force text+data — and hence the whole load — to a 256-byte boundary
 * and cap per-symbol alignment inside .bss at a WORD (SUBALIGN 2), so .bss abuts text+data exactly
 * while the 256-aligned load base keeps the image page-aligned.
 *
 * IT IS SUBALIGN(2) AND NOT SUBALIGN(1), AND THE DIFFERENCE IS AN ADDRESS ERROR. Packing .bss at
 * BYTE granularity strips the word alignment the 68000 requires of every `move.w`/`move.l`, so a
 * longword in .bss lands on an odd address whenever the object before it has odd size, and the
 * program dies at its first store to it. Nothing in the C can defend against it, because SUBALIGN
 * overrides a variable's own `__attribute__((aligned))`, and the dice are re-rolled by any edit
 * that changes an object's size — TOSBENCH's `read_buffer` is the only large .bss datum here today,
 * and it is one `static uint8_t` away from having an odd-sized neighbour. The cap costs at most one
 * padding byte per object and moves nothing else: the dot is already 256-aligned when `.bss` opens,
 * so a 2-aligned output section still abuts text+data exactly. The surface that would catch the
 * fault is a capture run of either program (`python3 tostest.py capture`, `tosbench.py capture`):
 * a program that dies at its first BSS store never publishes the ledger magic the driver waits for.
 *
 * COPIED FROM projects/wonderboy/recreate/atari/tos.ld, which is itself a copy of Joust's, and the
 * edits are this comment and the KEEP's object name (`os.o` here, since this directory's Makefile
 * names objects after their source file). The layout is otherwise identical and a change to it
 * belongs in all of them; copied rather than moved into `tools/recreate_kit/` for mkprg.py's
 * reason, and it is the same tracked kit-candidate debt.
 */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS
{
  . = 0;
  .text : {
    /* THE KEEP IS os.S's WHOLE `.text` — `_start` and the seventeen TOS trap wrappers. It names
     * THAT ONE OBJECT and not `*(.text)`, which would root every plain `.text` in the link,
     * libgcc's members included, and reorder the placement. Inert twice over today: this
     * directory's links carry no `--gc-sections`, so nothing is collected at all, and every
     * wrapper is reached by a call a relocation names anyway. It is here for the shape the file
     * takes as this project grows a code path entered from the VECTOR TABLE — a VBL or ACIA
     * handler, which no relocation names and a collector therefore cannot see — because that
     * failure is a machine that hangs, not a link that complains. */
    KEEP(*os.o(.text))
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

