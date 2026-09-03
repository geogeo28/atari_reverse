# Hardware Map

ST games spend most of their code talking to hardware directly, not the OS. An absolute
access to I/O space is unambiguous ground truth: a routine that writes `$ffff8240` **is**
a palette routine. Two access forms:

- short absolute `.w`: `$8240.w` — the `0xFFFF` high word is implied by sign extension.
- via register: `lea $ffff8240,a0; move.w d0,(a0)` — appears as an `abs.l` load `$ffff8240`.

Grep the disassembly / decomp for both (`\$ff(ff)?8[0-9a-f]{3}`, `\$fffffaxx`, `\$fffffc0x`).

## I/O memory map (the parts games use)

| Range | Chip / role | Notable regs |
|-------|-------------|--------------|
| `$ffff8200–8260` | **Video / Shifter** | `8201/8203` video base hi/mid, `820A` sync mode, `8240–825E` palette (16 words), `8260` resolution |
| `$ffff8800/8802` | **YM2149 PSG** | sound, and reads for joystick/keyboard/drive via port A/B → see `sound.md` |
| `$ffff8604–860D` | **DMA / disk** | floppy/HD |
| `$ffff8900–8925` | **STE DMA sound** + the LMC1992 mixer on MicroWire | `8901` control, `8903/05/07` start, `890F/11/13` end, `8921` mode; `8922` MicroWire data, `8924` mask — below |
| `$fffffa00–fa2F` | **MFP 68901** | timers A–D, interrupt enable/mask, `fa01` GPIP |
| `$fffffc00/fc02` | **IKBD ACIA** | keyboard/mouse/joystick controller (status/data) |

Palette word = ST `0x0RGB` (3 bits/channel) or STE 4-bit — see `graphics.md`.

### The STE sound block

Two traps in its shape. Every DMA *address* register is a **byte at an ODD address** — the chip
presents its 24-bit pointers as three bytes with a gap, so a `move.l` writes the wrong three. And
the block is only half the story: the samples and the YM both leave the machine through the
**LMC1992** volume/tone/mixer chip on the MicroWire bus (`$ffff8922` data, `$ffff8924` mask),
which TOS leaves wherever the last program put it. Routing it is not optional and the failure is
silent — [`sound.md`](sound.md), "The STE's mixer" has the word format and the one measured mixer
value. Whether any of this exists is the **cookie jar**'s answer, not an assumption:
[`tos-os-calls.md`](tos-os-calls.md), "Which machine is this?".

## Screen basics

Low-res = 320×200, 16 colours, **4 bitplanes, word-interleaved**, 32000 bytes. Physical
screen base is set via XBIOS `Setscreen`/`Physbase` or by writing `$ffff8201/8203`
directly. **Double buffering** = keep two screen buffers and flip the base each frame:
BuggyBoy's `flip_screen` toggles an index and writes the base to `$ffff8200`, then Vsyncs.

## Interrupts & low memory

- **VBL** (50/60 Hz vertical blank) drives per-frame work. Games chain a handler onto the
  VBL queue: `_nvbls` at **`0x454`** (count), `_vblqueue` at **`0x456`** (pointer to the
  routine-pointer array). BuggyBoy installs its **sound `REFRESH`** routine here.
  **Prefer a queue slot to taking vector `$70` outright**: TOS's own level-4 handler reloads the
  shifter's screen base from `_v_bas_ad`, runs the cursor and mouse timers, honours `_vblsem` and
  counts `_frclock`, so owning `$70` means reproducing all of that or breaking it — while a queue
  entry runs after the housekeeping, in supervisor mode (which the PSG and DMA registers need), and
  not while `_vblsem` is set. The case to plan for is **no free slot**: accessories can take them
  all, and a program whose frame clock, page flip and music all hang off the blank has no degraded
  mode to fall back to. BLACK ICE chains the level-4 autovector in that case, which is only safe
  because its own base-setting writes `_v_bas_ad` too (`projects/blackice/atari/README.md`, "The
  iron list" — *iron only*: Hatari's EmuTOS always leaves slot 0 free, so the fallback has never
  run).
- **MFP timers** (`Xbtimer`, vectors `$100+`) — often the music/timer tick.
- Low-memory system vars worth knowing: `0x420` memvalid, `0x4A2` _v_bas_ad (screen base),
  `0x484` **conterm** (keyboard/click config — games zero it), `0x466` _dumpflg.
- Supervisor mode via GEMDOS `Super` or XBIOS `Supexec` is needed to touch most of this.

## Line-A

The ST's low-level graphics primitives, invoked by opcodes `$A000–$A00F` — illegal
instructions the OS traps. Treat an `$A0xx` word as a Line-A call, not data. BuggyBoy's
loader uses `$A000`/`$A00A`/`$A00D` = **init / hide mouse / draw sprite**.

Full opcode table: [`tos-os-calls.md`](tos-os-calls.md), "Line-A". A Line-A word also
**halts Ghidra's disassembler** — see [`ghidra-pipeline.md`](ghidra-pipeline.md),
"Line-A opcodes".

→ Assets: [`graphics.md`](graphics.md), [`sound.md`](sound.md).