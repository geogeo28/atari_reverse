# 68000 Disassembly

The ST CPU is the Motorola **68000**: 16/32-bit, big-endian, 8 data (D0–D7) + 8
address (A0–A7) registers; A7 = stack. Instructions are 1+ 16-bit words.

## Why a "first-pass" linear sweep is tricky

A linear sweep decodes forward word-by-word. The danger is **instruction length**: if
you miscount one instruction's length you desync and everything after is garbage. Length
depends on the operand **effective-address (EA) mode** and its extension words:

| EA mode (bits) | Extension words |
|----------------|-----------------|
| Dn / An / (An) / (An)+ / -(An) | 0 |
| d16(An) / d8(An,Xn) | 1 |
| abs.w / d16(PC) / d8(PC,Xn) | 1 |
| abs.l | 2 |
| immediate | 1 (byte/word) or 2 (long) |

`tools/prg_dis.py` computes lengths from these rules, so its sweep stays in sync through
real code. It falls back to `dc.w` for unknown opcodes and annotates traps.
**But**: it cannot tell code from data. In a 48 KB game, data regions (tables, strings,
bitmaps) decode as nonsense — that's expected. Use `prg_dis.py` for orientation and the
entry region; use **Ghidra** (which follows references) for real function recovery.

Run a slice:
```bash
python3 tools/prg_dis.py bin/GAME.PRG --start 0x<fileoff> --len 0x<n>
```
(`prg_dis` addresses are image-relative = file_offset − 28.)

## The "impossible instruction" tell

If a listing shows an instruction the 68000 **cannot encode**, the decoder is wrong — not
the binary. The most useful case is the *destination register class*: only `MOVEA`, `ADDA`,
`SUBA`, `CMPA` and `LEA` may target an address register. So **`and.w #imm,a0`,
`or.w <ea>,a1` and `eor.b d0,a2` do not exist**; seeing one means those bits are really some
other instruction (or plain data). A bit op on an address register (`btst d0,a0`) is the same
tell — bit ops cannot address `An`, so that encoding is really `MOVEP`.

The `Dn -> <ea>` direction of `AND`/`OR`/`ADD`/`SUB` additionally cannot use ea mode `000`
(`Dn`) — those encodings are `ABCD`/`SBCD`/`EXG`/`ADDX`/`SUBX`. But that half is **not**
visible in a listing: `and.w d0,d1` *is* a legal instruction (`AND.W <ea>,Dn`, opmode `001`),
and both directions print the same text, so only the opcode word's opmode field can tell them
apart. The `An` destination is the half you can spot by eye.

In the 0x8xxx (`OR`) and 0xCxxx (`AND`) groups this bites hard, because the 3-bit opmode
field is *not* laid out like `ADD`/`SUB`:

| opmode | lines 9 / B / D | lines 8 / C |
|--------|-----------------|-------------|
| `011`  | `SUBA.W` / `CMPA.W` / `ADDA.W` — `<ea>,An` | **`DIVU.W` / `MULU.W` — `<ea>,Dn`** |
| `111`  | `SUBA.L` / `CMPA.L` / `ADDA.L` — `<ea>,An` | **`DIVS.W` / `MULS.W` — `<ea>,Dn`** |
| `100` (ea mode `000`/`001`) | `SUBX.B` / `CMPM.B`¹ / `ADDX.B` | **`SBCD`** (line 8) / **`ABCD`** (line C) |
| `101`, `110` (ea mode `000`/`001`) | the same, `.W` / `.L` | line 8: illegal. line C: **`EXG`**² |

¹ `CMPM` needs ea mode `001` (postincrement) — line B with ea mode `000` is an ordinary
`EOR.x Dn,Dn`, not an impossible form.
² the three legal `EXG` encodings are `101`+`000` (`Dx,Dy`), `101`+`001` (`Ax,Ay`) and
`110`+`001` (`Dx,Ay`); opmode `110`+`000` would be `EXG`'s nonexistent opmode `10000`, so it is
illegal (`prg_dis` prints it as `and.l dX,dY` — indistinguishable from the legal `<ea>,Dn` form).

This is a **length** bug as well as a mnemonic one: read as an `xxxA.L` form, opmode `111`
consumes a 4-byte immediate where `MULS.W #imm,Dn` has only 2 — enough to desync the sweep.
`prg_dis` got this wrong until 2026-07-28; it silently turned Joust's coordinate math
(`mulu.w #$a0,d0` = y × 160, `divu.w #$10,d0` = x ÷ 16) into meaningless masking.
`tools/recreate_kit/test/test_prg_dis.py` pins the encodings; run the kit's suite after touching
the decoder: `cd tools/recreate_kit && make test`.

`MOVEP` was the same family's other **length** bug, fixed the same day: `0000 rrr 1 1xx 001 aaa`
plus a displacement word = 4 bytes, which `prg_dis` read as a 2-byte dynamic bit op (`btst d0,a0`).

Still knowingly unhandled in `prg_dis`, all *mnemonic-only* — ea modes `000`/`001` take no
extension word, so the length is right and the sweep stays in sync: `ABCD`/`SBCD` (printed as
`and.b`/`or.b` into an `An`), `ADDX`/`SUBX` (as `add`/`sub`), and `CMPM` (as `eor`). The test
above sweeps all 65536 opcode words for this impossible-destination tell and allowlists exactly
those 832 encodings, so any *new* one fails the moment it appears.

## Idioms you'll see constantly

- `dbf Dn,label` (a.k.a. `dbra`) — decrement-and-loop; the workhorse loop. `Dn` counts
  down to −1.
- `movem.l regs,-(sp)` / `movem.l (sp)+,regs` — save/restore register sets.
- `lea $xxxxxxxx.l,An` — load an **absolute** address (this longword is relocated).
- `pea x(pc)` / `pea $abs.l` then `move.w #fn,-(sp)` then `trap #N` — an OS call.
- `link/unlk A6` — stack frame; `A6`-relative locals.

## Jump tables (control flow you must decode by hand)

Two shapes, both common in ST games:

1. **Offset table**: `move.w (tbl,Dn.w*2),Dm; jmp (tbl,Dm.w)` — each entry is a signed
   16-bit offset added to the table base. Handler = `tbl + offset`. BuggyBoy's course-event
   dispatcher (129 entries) and object-type dispatcher are both this. Decode the words,
   add the base, and you get every handler address (see `methodology.md` for the script).
2. **Pointer table**: array of absolute addresses (each is relocated) indexed and `jsr`ed.

Ghidra's "Decompiler Switch Analysis" recovers many of these automatically after the
relocation table is applied; the rest you decode from the raw words.

## Machine detection

ST-family games often branch on machine type via `$ffff8007` (STE/MSTE bus) or the
`_cookie` jar. BuggyBoy's `START.PRG` printed `ST/STE/Mega STE/TT/Falcon`, MHz, and TOS
version — such strings pinpoint the detection routine.

→ Next: [`ghidra-pipeline.md`](ghidra-pipeline.md) (recover real functions),
[`tos-os-calls.md`](tos-os-calls.md) (what the traps mean).