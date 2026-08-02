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

### A desynced sweep **drops** instructions — never take a census from a listing

Desync does not only print nonsense from the desync point on. It swallows the real instructions
that follow into the extension words of a bogus one, so they are **absent from the listing
altogether** — and the listing simultaneously invents instructions inside data. Any question of the
form *"does this program ever do X?"* must therefore be answered by a **byte scan of text+data**,
never by grepping a listing. A byte scan can over-count (data that happens to spell the opcode),
which is the safe direction for a "never does X" claim; a listing under-counts, which is not.

The worked case is Joust's trap census. A byte scan of text+data at even alignment finds **72**
`4e4<n>` words: 22 `trap #1`, 1 `trap #2`, 2 `trap #7`, 9 `trap #13`, 35 `trap #14`, 3 `trap #15`.
`prg_dis`'s listing shows **71** — the same set minus one `trap #13`, the `4e4d` at image `0x11c2c`
(a BIOS `Bconstat`: `3f3c 0002 / 3f3c 0001 / 4e4d`), which is real code a desync rendered as
`ori.b #$4e4d,d1`. That is the whole of the listing's under-count, and it is the dangerous
direction: a "never does X" claim read off the listing would have missed a live OS call.

The over-count is in **both** sources, so it is not a listing artefact — those two `trap #7` and
three `trap #15`, *and* the lone `trap #2`, are all ASCII pairs inside string tables that happen to
live in the text segment. Six spurious lines in total:

| bytes | image | ASCII | inside |
|---|---|---|---|
| `4e4f` | `0x102c0` | `NO` | `MONO.ERR` (a filename) |
| `4e47` | `0x1830c`, `0x1834c` | `NG` | `CONGRATULATIONS!` |
| `4e42` | `0x18500` | `NB` | `BEWARE OF THE UNBEATABLE PTERODACTYL` |
| `4e4f` | `0x18556`, `0x18588` | `NO` | `NO BONUS AWARDED` |

So the real census is 22 `trap #1` + 9 `trap #13` + 35 `trap #14` = **66** OS calls, and every one
of the 72 raw hits had to be classified by reading its bytes. Do not assume the extra trap *numbers*
are the spurious ones and the "plausible" ones real: `trap #2` is a legitimate GEM vector on the ST,
which is exactly why counting it as code went unnoticed.

To census OS calls properly, scan for each `4e4<n>` opcode word and then read the `3f3c <sel>`
selector immediate a compiler emits directly in front of it — checking that *every* site has one,
so no selector is loaded through a register where the scan could not see it. A hit with no selector
in front of it is the tell for an ASCII (or other data) misdecode.
`projects/joust/recreate/project.toml` records exactly that scan as the evidence for its
`tos_malloc_unused` waiver.

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

## Semantics that silently change a reconstruction

Three 68000 behaviours a C reconstruction has to model explicitly. None of them shows in the
mnemonic — the listing reads as ordinary arithmetic — and each yields a *plausible wrong answer*
rather than a crash, so nothing draws attention to them.

**A relocated *immediate operand*.** The DRI relocation table fixes up 32-bit longwords by image
offset, and nothing requires the longword to be a pointer sitting in data: it can be the immediate
field of an instruction. `cmpi.l #$00007832,d0` assembled against a text base of 0 becomes
`cmpi.l #$00017832,d0` once loaded at `0x10000`. Disassemble the *unrelocated* file and you get a
constant that is off by the load base, with no impossible instruction and no desync to warn you —
just a magic number that looks fine. Joust's `rng_advance` bounds its pointer with `#$17832` and
resets it to `#$10000`, both of which print as `#$7832` and `#$0` in a raw listing.

So: always disassemble the **relocated** image (`recreate_kit/oracle/loader.py` applies the fixups;
Ghidra's `PrgLoader` does too), and when a constant lands suspiciously near the load base, check
whether its own image offset is in the relocation table. See
[`binary-formats.md`](binary-formats.md) for the table's format.

**`ADDA.W <ea>,An` adds only the low word, SIGN-EXTENDED.** The source's high word is discarded and
a source with bit 15 set *subtracts*: `adda.w #$ffa0,a0` moves A0 back 96 bytes, not forward 65440.
A C reconstruction writing `addr += offset` for a 32-bit `offset` is a different instruction; the
faithful form is `addr += (int16_t)offset`. Joust's `pos_to_screen` folds both of its offsets in
this way, so from y = 205 its screen address runs *backwards* — off-screen, and reproduced rather
than fixed. (`ADDA.L` takes the whole longword; only the `.W` form truncates.)

**`DIVU.W` / `DIVS.W` overflow leaves the destination register UNTOUCHED.** When the quotient will
not fit in 16 bits the 68000 sets V and **does not write Dn at all** — the dividend stays there
intact, neither quotient nor remainder. (Division by zero is a different case again: a trap through
vector 5.) A reconstruction that unconditionally computes `dn = (remainder << 16) | quotient`
diverges on exactly the inputs the original leaves alone. Joust's `screen.c` therefore routes both
divides through one `divu_w()` helper that returns the dividend on overflow. Code that never tests
V after the divide — most compiled code — silently carries the dividend forward as if it were a
result, so this is a faithfulness question, not an error path.

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

## `addq.l #n,(a7)` — a callee that skips its caller's next call

The other control flow a decompiler will not show you, and unlike a jump table it leaves
no table to decode. A subroutine adds a constant to **its own return address** before the
`rts`, so it returns *past* the instructions that follow the `bsr` that called it:

```
75fc: clr.b   $8233.l
7602: bsr.w   $79d2          ; return address = $7606
7606: bsr.w   $7c08          ; ...which this callee can decide to skip
760a: rts
...
79d2: move.w  $83ae.l,d0
79d8: cmp.w   $83b2.l,d0
79de: bne.w   $79e6
79e2: addq.l  #4,(a7)        ; $7606 -> $760a: the caller's second bsr never happens
79e4: rts
```

One act means both "I had nothing to do" and "skip the work that would have followed me".
Three consequences worth knowing before you meet one:

- **Ghidra models none of it.** `decomp.c` shows a bare `return` for the arm that skips
  and an unconditional pair of calls in the caller, so the reconstruction reads correct
  and behaves wrong. The disassembly is the only place the fact exists.
- **A hardware/leaf scan still classifies the callee correctly** (it has an `rts`, no
  hidden callee, no hardware) — this is not a scan blind spot, it is a *decompiler* one.
- **It breaks an oracle-style harness entered at the callee.** A differential runner stops
  when the PC reaches a sentinel it pushed as the return address; the skipping arm returns
  to *sentinel + n* and the run never stops. Give the runner that second stop PC, and read
  the decision back off the stack the callee rewrote — which pins the skip on the original
  as well as on the reconstruction. `projects/wonderboy/recreate/test/test_scroll.py` is
  the worked example; in C the callee has to become a function that RETURNS the decision.

Grep for it directly: `addq.l #n,(a7)` is `5x97` (`5097` = #8, `5897` = #4, `5297` = #1),
and `addq.w`/`addi.l` forms exist too. **The encoding decides it, with no reading of the
surrounding code.** The low byte is the destination's effective address: `97` is *memory
at `(a7)`*, so a `5x97` REWRITES the longword sitting at the stack top — the return
address, wherever A7 has not moved since the `bsr`. Argument cleanup is the other
encoding, `5x8F` (`addq.l #n,a7`; `5x4F` for the word form, `4FEF` for `lea n(a7),a7`),
which adjusts the POINTER and leaves the longword it points at untouched. A `5x97` is
therefore never cleanup, and a `5x8F` never this idiom.

## Machine detection

ST-family games often branch on machine type via `$ffff8007` (STE/MSTE bus) or the
`_cookie` jar. BuggyBoy's `START.PRG` printed `ST/STE/Mega STE/TT/Falcon`, MHz, and TOS
version — such strings pinpoint the detection routine.

→ Next: [`ghidra-pipeline.md`](ghidra-pipeline.md) (recover real functions),
[`tos-os-calls.md`](tos-os-calls.md) (what the traps mean).