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
| `$ffff8900–8925` | **STE DMA sound** | (STE only) |
| `$fffffa00–fa2F` | **MFP 68901** | timers A–D, interrupt enable/mask, `fa01` GPIP |
| `$fffffc00/fc02` | **IKBD ACIA** | keyboard/mouse/joystick controller (status/data) |

Palette word = ST `0x0RGB` (3 bits/channel) or STE 4-bit — see `graphics.md`.

## Screen basics

Low-res = 320×200, 16 colours, **4 bitplanes, word-interleaved**, 32000 bytes. Physical
screen base is set via XBIOS `Setscreen`/`Physbase` or by writing `$ffff8201/8203`
directly. **Double buffering** = keep two screen buffers and flip the base each frame:
BuggyBoy's `flip_screen` toggles an index and writes the base to `$ffff8200`, then Vsyncs.

## Interrupts & low memory

- **VBL** (50/60 Hz vertical blank) drives per-frame work. Games chain a handler onto the
  VBL queue: `_nvbls` at **`0x454`** (count), `_vblqueue` at **`0x456`** (pointer to the
  routine-pointer array). BuggyBoy installs its **sound `REFRESH`** routine here.
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