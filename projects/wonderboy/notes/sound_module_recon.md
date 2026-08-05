# Wonder Boy in Monsterland (ST) — sound module reconnaissance

Read-only recon of the self-contained PSG replay driver reached through `snd_stub_00`
(`$17adc`). Every claim below is cited to a runtime address; addresses are **Ghidra
addresses with this project's load base `0x3f8`** (see `projects/wonderboy/run.sh`).

**File-offset math (verified).** `file_offset = runtime_addr - 0x3dc`
(text starts at file `0x1c`, load base `0x3f8`, so `0x1c - 0x3f8 = -0x3dc`).
Anchor check: `$17adc -> file 0x17700` = `48e7 fffe 6100 0058 4cdf 7fff 4e75` — the
`movem.l #$fffe,-(a7)` of stub +0. The PRG is `bin/disk1/AUTO/SWB.PRG` (136979 B,
`text=0x214d8`).

**Method note.** `out/wonderboy_dis.txt` contains a complete *linear* first-pass sweep
(`--- first-pass disassembly (text: addr 0x3f8..0x218d0) ---`), so the module *is*
covered — but Ghidra renders every indexed addressing mode as the opaque token `idx`,
which hides exactly the table arithmetic this module is built out of. All disassembly
quoted here was therefore re-generated with `m68k-elf-objdump -D -b binary -m m68k:68000`
over the raw slice. Ghidra's *function* analysis never entered the module (only `lea
$17adc.l` reaches it), so `decomp.c` is useless here.

**The one structural correction to the brief.** The module is anchored on
`a3 = $1738c`, not `$17adc`: *every* routine starts with `lea $1738c(pc),a3` and all
data is addressed as `d16(a3)` or `(a3,Xn.w)`. `$1738c` is `$750` bytes *below* the
stub table. Nothing in the range `a3+0 .. a3+$c47` is ever read (lowest observed
a3-offset = `$0c48` = `$17fd4`), so `$1738c` is just the link origin of a larger blob;
the sound module proper is `$17adc..$1abc8` (4333 bytes), **not** `$17adc..$1ab04`
— `$1ab04..$1abc8` is the instrument table plus its envelope data.

---

## 1. ENTRY POINTS

The vector is a run of `movem`-wrapped thunks at `$17adc..$17b39`. Register sets differ
per stub (already correct in `names.txt`).

| Stub | Thunk | Target | Role | Inputs |
|---|---|---|---|---|
| +0  | `$17adc` | `$17b3a` | **PLAY SONG / init** | `d0.b` = song id 0..16 |
| +14 | `$17aea` | `$17c74` `snd_music_tick` | per-VBL tick (music + SFX + PSG out) | none |
| +28 | `$17af8` | `$17f24` | **STOP / silence** (resumable) | none |
| +42 | `$17b06` | `$17f82` | **RESUME** (unpause) | none |
| +56 | `$17b14` | `$1a48a` `snd_trigger_effect` | **PLAY SFX** | `d0.b` = SFX id 0..25, `d1.b` = channel |
| +70 | `$17b22` | `$1aaea` | **STOP ALL SFX** + PSG silence | none |
| +84 | `$17b30` | `$17f92` | **START FADE-OUT** | none (rate hardcoded 10) |

### +0 `$17b3a` — play song (this is "init")

```
17b3a: lea    %pc@(0x1738c),%a3
17b3e: bsrw   0x17af8            ; <-- calls stub+28 (STOP) first
17b42: clrb   %a3@(2264)         ; global transpose := 0
17b46: extw   %d0                ; d0 is a *byte* song id, sign-extended
17b48: muluw  #8,%d0             ; 8-byte song record
17b4c: lea    %pc@(0x18480),%a0  ; song directory
17b50: moveb  %a0@(1,%d0:w),%a3@(2252)   ; song speed  -> $17c58
17b56: moveb  %pc@(0x17c58),%a3@(2253)   ;             -> $17c59 (copy)
17b5c: lea    %pc@(0x17bc6),%a1  ; channel A state
17b60: moveq  #2,%d7             ; 3 channels
   ... per channel: +27 := 1, +0 := 0, +44 := 0, +45 := 0, +46 := 0,
       +16 = +20 := $1844e (null arpeggio), +6 := word at song_rec+2+2*ch,
       +10 := 2, +2 := $1738c + word at (a3 + that offset)   ; first pattern
17baa: clrl   %a3@(2258)         ; per-channel HW mute/lock flags := 0
17bae: moveb  #15,%a3@(2251)     ; master volume := 15
17bb4: sf     %a3@(2265)         ; fade rate := 0
17bb8: st     %a3@(2270)         ; speed accumulator := $ff
17bbc: st     %a3@(2263)         ; "song loaded / not ended" := $ff
17bc0: st     %a3@(2250)         ; ENGINE ENABLED := $ff
17bc4: rts
```

**Yes — +0 must be called before ticking.** `snd_music_tick` bails out immediately
(`$17ca0`/`$17ca6`) unless `a3+2250` (`$17c56`) or `a3+2254..2257` (`$17c5a`, the SFX
flags) is non-zero, and both are only set by +0 / +56. It also calls **+28 first**, so
"stop then start" is already inside it.

### +28 `$17f24` — stop (pause)
```
17f24: lea  %pc@(0x1738c),%a3
17f28: sf   %a3@(2250)     ; engine disabled
17f2c: braw 0x1aaea        ; -> clear SFX flags, zero volumes, mixer := $3f, PSG silence
```
It does **not** clear `a3+2263`, so +42 can restart it.

### +42 `$17f82` — resume
```
17f82: lea   %pc@(0x1738c),%a3
17f86: tstb  %a3@(2263)    ; only if a song is loaded and has not ended
17f8a: beqs  0x17f90
17f8c: st    %a3@(2250)
```

### +70 `$1aaea` — stop all SFX + silence
```
1aaea: lea   %pc@(0x1738c),%a3   ; (objdump misaligns here: the 4 PRNG bytes at $1aae6
                                 ;  swallow this opcode unless you disassemble from $1aaea)
1aaee: clrl  %a3@(2254)          ; the 3 SFX-active flags (+1 pad byte)
1aaf2: clrw  %a3@(4046)          ; PSG shadow vol A/B
1aaf6: clrb  %a3@(4048)          ; PSG shadow vol C
1aafa: moveb #63,%a3@(4045)      ; PSG shadow mixer := $3f (all tone+noise off)
1ab00: braw  0x17f30             ; psg_silence
```

### +84 `$17f92` — start fade-out
```
17f92: moveb #10,%a3@(2266)   ; fade countdown
17f98: moveb #10,%a3@(2265)   ; fade rate (0 = no fade)
```
The tick then decrements the master volume every 10 sub-ticks (`$17cc2..$17ce2`) and
**self-stops** via `$18016` when it reaches 0.

### `$17f30` — psg_silence (not a stub; tail of +28/+70)
Masks IRQs (`move.w #$2700,sr`), read-modify-writes PSG reg 7 with `or #$3f`, then
zeroes regs 8/9/10.

### Externally-polled state
`$00192c` does `lea $17adc.l,a5 / tst.b 378(a5) / bne.s` — `$17adc + 378 = $17c56`,
i.e. **the game busy-waits on the engine-enabled byte to detect "song finished"**.

---

## 2. TRIGGER CONVENTION — `snd_trigger_effect` `$1a48a`

**Inputs: `d0.b` = SFX id, `d1.b` = channel.** `d1` selects one of three otherwise
identical code paths:

```
1a48e: cmpb #0,%d1 / bnes 0x1a4fe   ; d1 == 0 -> channel A  ($1a494)
1a4fe: cmpb #1,%d1 / bnes 0x1a56e   ; d1 == 1 -> channel B  ($1a504)
1a56e:                              ; anything else -> channel C
```

Indexing (channel-A path; B/C identical with +$1a on the state block):
```
1a498: extw  %d0                    ; SFX id is a *byte*, sign-extended
1a49a: addw  %d0,%d0                ; *2
1a49c: lea   %pc@(0x1a830),%a0      ; SFX pointer table
1a4a0: moveaw %a0@(0,%d0:w),%a0     ; a3-relative word offset
1a4a4: addal %a3,%a0                ; -> descriptor address
1a4a6: moveq #13,%d0
1a4a8: lea   %pc@(0x1aa7c),%a1      ; channel-A SFX state
1a4ac: moveb %a0@+,%a1@+ / dbf      ; copy 14 bytes
...
1a4d8: moveb %pc@(0x1aa86),%d0      ; descriptor+10 = volume-stream index
1a4de: addw  %d0,%d0
1a4e0: lea   %pc@(0x1a9d0),%a2      ; volume-stream pointer table
1a4e4: moveaw %a2@(0,%d0:w),%a2 / addal %a3,%a2
1a4ea: movel %a2,%a3@(14082)        ; loop base
1a4ee: movel %a2,%a3@(14086)        ; current pointer
1a4f2: moveb %a2@,%a3@(4060)        ; first volume -> SFX ch-A volume
1a4f6: moveb #1,%a3@(2254)          ; SFX ch A active
```

**Tables**

| Table | Base | Stride | Count | Extent |
|---|---|---|---|---|
| SFX pointer table | `$1a830` | 2 (word, a3-relative) | **26** (`$00..$19`) | `$1a830..$1a863` |
| SFX descriptors | `$1a864` | **14** | 26 | `$1a864..$1a9cf` |
| SFX volume-stream ptrs | `$1a9d0` | 2 (word, a3-relative) | **10** (`0..9`) | `$1a9d0..$1a9e3` |
| SFX volume streams | `$1a9e4` | var | 10 | `$1a9e4..$1aa7b` |

The counts are **exact and self-proving**: entry 0 of the pointer table resolves to
`$1a864` (immediately after the table); 26 × 14 = 364 lands exactly on `$1a9d0`; entry
0 of the volume table resolves to `$1a9e4` (immediately after that table); and every
descriptor's `+10` field is in `0..9`. There is **no bounds check** — an id ≥ 26 reads
garbage.

**MUSIC and SFX are separate id spaces.** Songs go through +0 and index `$18480`
(stride 8, 17 entries); SFX go through +56 and index `$1a830` (stride 2 → 26
descriptors). `d0 = $f` therefore means *song 15* at `$00191e` and *SFX 15* at
`$00bc9c`.

**SFX descriptor layout (14 bytes)** — field roles read off `$1a48a` and the tick at
`$1a602`:

| Off | Role |
|---|---|
| +0 | overall duration counter |
| +1 | period-step reload (→ state +14) |
| +2..3 | base tone period (word) |
| +3 | *also* the noise period, written when `+6` bit 3 is clear |
| +4..5 | pitch-slide amount (word) |
| +6 | PSG mixer bits for this channel (1 = off, matches PSG polarity) |
| +7 | non-zero → take the pitch delta from the module's PRNG (`$1aae6`) |
| +8 | slide direction (`bpl`/`bmi` at `$1a670`) |
| +9 | slide countdown |
| +10 | volume-stream index (0..9) |
| +11 | volume step reload (→ state +15) |
| +12 | sustain/hold flag |
| +13 | secondary counter reload (→ state +16) |

The 26 descriptors, verbatim:
```
sfx  0 $1a864 0f 0e 03 02 00 29 fe 00 01 00 00 03 00 00
sfx  1 $1a872 1e 63 00 82 00 08 fe 00 ff 63 08 06 00 03
sfx  2 $1a880 0f 63 01 90 00 20 f6 00 ff 63 05 01 00 00
sfx  3 $1a88e 32 0a 00 a0 00 18 fe 00 ff 63 08 05 00 02
sfx  4 $1a89c 28 01 01 5e 00 01 fe 00 ff 63 09 01 00 00
sfx  5 $1a8aa 19 18 04 02 00 29 fe 00 01 00 00 06 00 00
sfx  6 $1a8b8 19 05 01 02 00 20 fe 00 01 63 00 03 00 00
sfx  7 $1a8c6 14 63 01 20 00 10 fe 00 01 63 00 05 00 02
sfx  8 $1a8d4 0c 02 00 3c 00 02 fe 00 01 63 08 02 00 00
sfx  9 $1a8e2 0c 63 00 4c 00 00 fe 00 01 63 05 02 00 00
sfx 10 $1a8f0 28 03 01 42 00 29 f6 00 ff ff 00 03 00 00
sfx 11 $1a8fe 28 05 01 80 00 20 fe 00 01 63 00 03 00 02
sfx 12 $1a90c 1e 04 00 00 00 06 f7 01 ff 63 00 02 00 00
sfx 13 $1a91a 06 63 0a 12 00 22 f6 00 ff 00 00 01 00 00
sfx 14 $1a928 05 05 01 98 00 42 f6 00 ff 63 00 01 00 00
sfx 15 $1a936 46 05 05 02 09 29 fe 00 01 63 00 05 00 00
sfx 16 $1a944 07 63 00 0e 00 02 f7 00 01 63 02 01 00 00
sfx 17 $1a952 1e 0f 00 10 00 01 f7 00 ff 00 00 03 00 00
sfx 18 $1a960 2c 02 00 d8 00 02 fe 00 01 63 08 03 00 00
sfx 19 $1a96e 1e 06 00 40 00 06 fe 00 01 63 00 02 00 00
sfx 20 $1a97c 0a 05 01 82 00 28 f6 01 ff ff 08 01 00 00
sfx 21 $1a98a 19 09 00 34 00 07 f6 01 ff 0a 08 02 00 00
sfx 22 $1a998 1e 0a 08 00 04 00 fe 00 ff 00 00 06 00 0a
sfx 23 $1a9a6 06 63 00 10 00 02 f7 00 ff 63 08 01 00 00
sfx 24 $1a9b4 5a 02 00 1d 00 01 f7 00 ff 63 01 04 00 00
sfx 25 $1a9c2 50 09 00 60 00 04 fe 00 01 63 08 08 00 00
```

---

## 3. CALL SITES — the game's actual id inventory

`lea $17adc.l,aN` appears at **exactly 25 sites**, and a scan of the whole disassembly
confirms **`$17adc` is the only address in `$1738c..$1abd0` referenced from outside the
module**. Nothing else pokes the driver's data.

| Site | Stub | `d0` | `d1` | Meaning |
|---|---|---|---|---|
| `$00058e` | +84 | — | — | fade out |
| `$000720` | +14 | — | — | **the VBL tick** (inside `vbl_handler` `$716`) |
| `$000a98` | +56 | `$16` (22) | 0 | SFX 22, ch A |
| `$000ae2` | +0  | `$10` (16) | — | **song 16** |
| `$000c42` | +56 | `$05` | 0 | SFX 5, ch A |
| `$000c90` | +28 | — | — | stop |
| `$000ca0` | +56 | `$05` | 0 | SFX 5, ch A |
| `$000e82` | +56 | `$00` | 0 | SFX 0, ch A |
| `$00169c` | +56 | `$01` | 0 | SFX 1, ch A |
| `$001726` | +56 | `$03` | 0 | SFX 3, ch A |
| `$0017bc` | +56 | `$03` | 0 | SFX 3, ch A |
| `$00191e` | +0  | `$0f` (15) | 0 | **song 15** |
| `$00192c` | —   | — | — | `tst.b 378(a5)` = poll `$17c56`, spin until song ends |
| `$001982` | +28 then +56 | `$04` | 0 | stop, then SFX 4 ch A |
| `$0020ee` | +56 | `$06` | 0 | SFX 6, ch A |
| `$00542c` | +56 | `$09` | 0 | SFX 9, ch A |
| `$00678c` | +56 (`jmp`) | `$09` | 0 | SFX 9, ch A |
| `$00679c` | +56 | `$08` | 0 | SFX 8, ch A |
| `$006ae4` | +56 | `$0b` | 0 | SFX 11, ch A |
| `$006bca` | +28 | — | — | stop (in `$6bb8`) |
| `$006be2` | +56 | `$19` (25) | 0 | SFX 25, ch A (in `$6bb8`) |
| `$006fb0` | +0  | `$0e` (14) | 0 | **song 14** |
| `$00bc9c` | +56 | `$0f` (15) | 0 | SFX 15, ch A (in `$bbca`) |
| `$00e54a` | +0  | `$08` | — | **song 8** |
| `$00f9fc` | +0 / +28 | **data-driven** | — | see below |

**Every SFX call site passes `d1 = 0`** (`clr.w d1`) — the game only ever uses channel A
for effects; the ch-B and ch-C paths of `$1a48a` are dead in this build.

`$00f9fc` is the level-music dispatcher:
```
00f9fc: lea    $17adc.l,a1
00fa02: moveq  #0,d0
00fa04: move.b 8(a0),d0        ; music id from the room/level record
00fa08: bmi.w  $fa22           ; negative -> stop
00fa0c: cmp.b  $fa2e.l,d0      ; already playing this one?
00fa12: bne.w  $fa18
00fa16: rts
00fa18: move.b d0,$fa2e.l      ; remember current song
00fa1e: jsr    (a1)            ; stub+0 : play song d0
00fa22: move.b d0,$fa2e.l
00fa28: jsr    28(a1)          ; stub+28 : stop
```
So the full song inventory is data (17 songs, ids 0..16); `$fa2e` is the "currently
playing song" cache, and byte `+8` of each level record holds the id.

Direct SFX ids observed as immediates: **0, 1, 3, 4, 5, 6, 8, 9, 11, 15, 22, 25**.
Direct song ids as immediates: **8, 14, 15, 16** — the rest come from level data.

---

## 4. TEMPO BRANCH — `$17c74..$17cb4`

```
17c74: lea   %pc@(0x1738c),%a3
17c78: moveb #0,%a3@(2274)                 ; tempo skip := 0     (a3+2274 = $17c6e)
17c7e: btst  #7,0xfffa01                   ; MFP GPIP bit 7 = monochrome-monitor detect
17c86: bnes  0x17c90                       ;   bit7 SET -> colour monitor
17c88: moveb #72,%a3@(2274)                ;   bit7 CLEAR -> MONO: skip := $48
17c8e: bras  0x17ca0
17c90: btst  #1,0xff820a                   ; shifter sync mode, bit 1
17c98: bnes  0x17ca0                       ;   bit1 SET -> 50 Hz: skip stays 0
17c9a: moveb #43,%a3@(2274)                ;   bit1 CLEAR -> 60 Hz: skip := $2b
17ca0: tstb  %a3@(2250)                    ; engine enabled?
17ca4: bnes  0x17cac
17ca6: tstl  %a3@(2254)                    ; ...or any SFX active?
17caa: beqs  0x17c72                       ; no -> rts
17cac: moveb %pc@(0x17c6e),%d0             ; the skip value
17cb0: addb  %d0,%a3@(2275)                ; accumulate  (a3+2275 = $17c6f)
17cb4: bcss  0x17c72                       ; CARRY -> SKIP THIS TICK entirely
```

It is a **fractional tick-dropper**, not a tempo scaler. Carry ⇒ the whole tick
(including the SFX engine and the PSG output) is skipped.

| Monitor / sync | `$fffffa01` bit 7 | `$ffff820a` bit 1 | value written to `$17c6e` | drop rate | effective tick |
|---|---|---|---|---|---|
| Mono | **0** | (not read) | `$48` (72) | 72/256 = 28.1% | 71.2 × 0.719 ≈ **51.2 Hz** |
| Colour 60 Hz | 1 | **0** | `$2b` (43) | 43/256 = 16.8% | 60 × 0.832 ≈ **49.9 Hz** |
| Colour 50 Hz | 1 | **1** | `$00` | 0% | **50 Hz** |

**To force the 50 Hz colour path, both reads must be non-zero:**
* `$FFFFFA01` (aliased `$00FFFA01`) must return a byte with **bit 7 set** — e.g. the
  real-ST idle GPIP `$B9`/`$F9`/`$FF`, or simply `$80`.
* `$FFFF820A` (aliased `$00FF820A`) must return a byte with **bit 1 set** — `$02`.

**This is a live trap for the current harness.** With hardware reads returning 0, bit 7
of `$fffa01` is clear, so the driver takes the **mono** branch and installs `$48`.
Ticked at 50 Hz that drops 28% of ticks and plays every song ~28% too slow. A
zero-returning emulator does *not* silently land on 50 Hz.

Note the operands are 32-bit absolutes `$00FFFA01` / `$00FF820A` (the `$00FFxxxx`
I/O mirror), not `$FFFFxxxx` — the memory model must decode that alias.

**The kit now serves both, opt-in.** `emu.audio_capture(True)` reports the 50 Hz colour
profile on exactly these two reads and answers the `$ff8800` read-back from a modeled
YM2149 register file, so an extractor can drive the replayer under the oracle. It is off
by default and invalid for a differential (each answer is the model's invention, not the
game's data) — see `tools/recreate_kit/README.md`, "Opt-in: audio capture", and the
behaviour pinned in `recreate/test/test_audio_capture.py`.

---

## 5. PSG ACCESS INVENTORY

A byte-scan of the raw image for the constants `00ff8800` / `00ff8802` over
`$17000..$1ac00` finds **17 references to `$FF8800` and 15 to `$FF8802`, all inside
`$17e42..$17f7c`**, i.e. two contiguous blocks. There is no other PSG access anywhere
in the module. (`psg_set_drive_select` at `$624c` in the FDC driver is the only other
PSG toucher in the whole program.) **All accesses are `move.b`** — `$FF8800` = register
select (write) / register read-back (read), `$FF8802` = register data (write only).

### Block 1 — `snd_music_tick` PSG output, `$17e34..$17f20`
```
17e34: movew %sr,%d1 / movew #$2700,%sr      ; IRQs masked, SUPERVISOR required
17e3a: clrb  %d2                             ; d2 = mixer bits this module owns
17e3c: tstl  %a3@(2258)                      ; any channel HW-locked?
17e40: bnes  0x17e52
17e42: W $ff8800 <- #6      ;  reg 6  noise period
17e4a: W $ff8802 <- [$18358]
17e52: tstb  %a3@(2258)                      ; ch A not locked ->
17e58: W $ff8800 <- #0      ;  reg 0  A fine
17e60: W $ff8802 <- [$18352]
17e68: W $ff8800 <- #1      ;  reg 1  A coarse
17e70: W $ff8802 <- [$18353]
17e78: W $ff8800 <- #8      ;  reg 8  A volume
17e80: W $ff8802 <- [$1835a]
17e88: orib  #9,%d2                           ; claim mixer bits 0 (tone A) + 3 (noise A)
17e8c: tstb  %a3@(2259)                       ; ch B ->
17e92: W $ff8800 <- #2  ; 17e9a: W $ff8802 <- [$18354]
17ea2: W $ff8800 <- #3  ; 17eaa: W $ff8802 <- [$18355]
17eb2: W $ff8800 <- #9  ; 17eba: W $ff8802 <- [$1835b]
17ec2: orib  #$12,%d2                          ; bits 1 + 4
17ec6: tstb  %a3@(2260)                       ; ch C ->
17ecc: W $ff8800 <- #4  ; 17ed4: W $ff8802 <- [$18356]
17edc: W $ff8800 <- #5  ; 17ee4: W $ff8802 <- [$18357]
17eec: W $ff8800 <- #$a ; 17ef4: W $ff8802 <- [$1835c]
17efc: orib  #$24,%d2                          ; bits 2 + 5
17f00: W $ff8800 <- #7                         ; select reg 7 (mixer)
17f08: R $ff8800 -> %d0                        ; *** READ #1 *** current mixer
17f0e: moveb %pc@(0x18359),%d3                 ; shadow mixer
17f12: eorb  %d0,%d3
17f14: andb  %d2,%d3                           ; keep only the bits this module owns
17f16: eorb  %d0,%d3
17f18: W $ff8802 <- %d3                        ; merged write-back
17f1e: movew %d1,%sr
```

### Block 2 — `psg_silence` `$17f30..$17f80`
```
17f30: movew %sr,%d2 / movew #$2700,%sr
17f36: W $ff8800 <- #7
17f3e: R $ff8800 -> %d1                        ; *** READ #2 ***
17f44: orib  #$3f,%d1                          ; force all 6 tone/noise bits OFF
17f48: W $ff8802 <- %d1
17f4e: W $ff8800 <- #8   ; 17f56: W $ff8802 <- #0
17f5e: W $ff8800 <- #9   ; 17f66: W $ff8802 <- #0
17f6e: W $ff8800 <- #$a  ; 17f76: W $ff8802 <- #0
17f7e: movew %d2,%sr
```

### The two reads, and why they must be modelled

Both reads are `move.b $00FF8800,Dn` **immediately after selecting register 7**, i.e.
"read back the mixer". A latch model (return the last byte written to PSG register 7)
is sufficient and correct.

**If reads return 0 the module actively corrupts machine state.** Register 7 bits 6 and
7 are the *port A / port B I/O direction* bits, and port A carries the floppy
drive/side select lines that `psg_set_drive_select` (`$624c`) drives. At `$17f08` a
zero read makes the RMW collapse to `d3 = shadow & d2`, which clears bits 6/7 → port A
flips to *input* → drive select floats. At `$17f3e` a zero read yields `$3f`, which also
clears bit 7. So the reg-7 read-back is load-bearing for the FDC as well as for the
mixer, and is not optional.

No other hardware register — no MFP timer, no shifter palette, no DMA — is touched.

---

## 6. DATA LAYOUT

Full module map (`$17adc..$1abc8`, 4333 bytes; every boundary below is proven by a
pointer resolving exactly onto the next region's first byte):

| Range | Size | Contents |
|---|---|---|
| `$17adc..$17b39` | 94 | stub table (7 thunks; +84 is 10 bytes, the rest 14) |
| `$17b3a..$17bc5` | 140 | play-song / init |
| **`$17bc6..$17c55`** | 144 | **3 × 48-byte music channel state (MUTABLE, in-image)** |
| **`$17c56..$17c71`** | 28 | **module globals (MUTABLE, in-image)** |
| `$17c72..$17f23` | 690 | shared `rts`, `snd_music_tick`, PSG output |
| `$17f24..$17f2f` | 12 | stop |
| `$17f30..$17f81` | 82 | psg_silence |
| `$17f82..$17f91` | 16 | resume |
| `$17f92..$17fa3` | 18 | fade start |
| `$17fa4..$17fd3` | 48 | **pattern-opcode jump table — 24 words, opcodes `$80..$97`** |
| `$17fd4..$18105` | 306 | opcode handlers |
| `$18106..$18351` | 588 | channel pattern step + period/volume/vibrato/portamento |
| **`$18352..$1835c`** | 11 | **PSG register shadow, regs 0..10 (MUTABLE)** |
| `$1835d..$1835f` | 3 | pad |
| **`$18360..$1836a`** | 11 | **SFX mix values (MUTABLE)**: A period w, B period w, C period w, noise b, pad, A/B/C volumes |
| `$1836b..$1836d` | 3 | pad |
| `$1836e..$1842d` | 192 | **note period table — 96 words** |
| `$1842e..$1844d` | 32 | arpeggio pointer table (16 words, a3-relative) |
| `$1844e..$1847f` | 50 | arpeggio streams (`$1844e` = the null/default one) |
| `$18480..$18507` | 136 | **song directory — 17 records × 8 bytes** |
| `$18508..$18523` | 28 | per-song per-channel sequence tables (word offsets, `0000`-terminated) |
| `$18524..$1a489` | 8038 | **pattern data — 106 distinct patterns** |
| `$1a48a..$1a5d9` | 336 | `snd_trigger_effect` (3 channel paths) |
| `$1a5da..$1a82f` | 598 | SFX tick engine (`$1a602` chA, `$1a6bc` chB, `$1a776` chC) |
| `$1a830..$1a863` | 52 | SFX pointer table (26 words) |
| `$1a864..$1a9cf` | 364 | 26 SFX descriptors × 14 |
| `$1a9d0..$1a9e3` | 20 | SFX volume-stream pointers (10 words) |
| `$1a9e4..$1aa7b` | 152 | SFX volume streams |
| **`$1aa7c..$1aac9`** | 78 | **3 × 26-byte SFX channel state (MUTABLE)** |
| `$1aaca..$1aae5` | 28 | PRNG step (`roxl` pair) |
| **`$1aae6..$1aae9`** | 4 | **PRNG state (MUTABLE)**, image value `b8 b9 42 12` |
| `$1aaea..$1ab03` | 26 | stop-all-SFX (+70) |
| `$1ab04..$1ab23` | 32 | instrument (volume-envelope) pointer table — 16 words |
| `$1ab24..$1abc8` | 165 | instrument envelope data (each preceded by a speed byte) |

`$1abc9` is `00`; `$1abca` is `4e71` (`nop`) and belongs to something else.

### Note period table (`$1836e`, 96 entries) — verified as equal temperament
```
entry 0 = 3822, entry 1 = 3607  -> ratio 1.0596 (semitone = 1.05946)
entry 0 / entry 12 = 2.0000     -> exact octave
f = 2 000 000 / 16 / 3822 = 32.71 Hz = C1
```
8 octaves, C1..B8. Lookup is `index = (note * 2) & $ff` (`addb %d0,%d0` at `$1825e`),
so notes ≥ 96 alias.

### Song directory (`$18480`, 17 × 8)
```
byte +0    : unused (always 0)
byte +1    : song speed  -> a3+2252 ($17c58)
word +2    : ch A sequence-table offset (a3-relative)
word +4    : ch B
word +6    : ch C
```
```
 0 00 30 1180 117c 1184      9 00 31 1f00 1ef8 1f08
 1 00 27 12d0 12cc 12d4     10 00 31 20ce 20ba 20e2
 2 00 40 1394 138e 139a     11 00 31 2308 22f6 231a
 3 00 30 14a8 1476 14b2     12 00 19 24b4 24b0 24b8
 4 00 20 15ac 15a8 15b0     13 00 31 2642 263a 264a
 5 00 30 1612 160e 1616     14 00 31 2a8e 2a76 2aa6
 6 00 39 18f0 18ec 18f4     15 00 d2 307a 3076 307e
 7 00 27 1a7c 1a72 1a86     16 00 31 3096 3092 309a
 8 00 31 1d10 1d08 1d18
```
Record 17 (`$18508`) is already sequence data — **17 songs, ids `$00..$10`**.

The speed byte is a fractional row-rate: `$17cea` adds it to an 8-bit accumulator
(`a3+2270`) every tick and steps all three channels on carry. `$30` ≈ every 5.3 ticks;
`$d2` (song 15) ≈ every 1.2; `$19` (song 12) ≈ every 10.

### Pattern byte-stream format (from `$18116` / `$181a6`)

| Byte | Meaning |
|---|---|
| `$00..$7f` | note number (index into the 96-entry period table) |
| `$80..$97` | command — `(b & $7f) * 2` indexes the jump table at `$17fa4`, `jmp (a3,offset.w)` |
| `$98..$bf` | **out of range** — would index past the 24-word table into code |
| `$c0..$cf` | select arpeggio 0..15 (table `$1842e`) |
| `$d0..$df` | select instrument 0..15 (table `$1ab04`; the byte *before* the data is the envelope speed) |
| `$e0..$ff` | set note duration = `b - $e0 + 1` (1..32) |

Command table (all 24 resolved and read):

| Op | Handler | Operands | Effect |
|---|---|---|---|
| `$80` | `$180ec` | 0 | **rest** (volume := 0, reload duration) |
| `$81` | `$180de` | 0 | portamento off (`ch+44 := 0`) |
| `$82` | `$180d6` | 0 | portamento on (`ch+44 := $40`) |
| `$83` | `$180e4` | 0 | set `ch+0` bit 1 |
| `$84` | `$1809c` | 2 | vibrato on: depth `ch+24`, speed `ch+25` |
| `$85` | `$180c2` | 0 | pitch slide on (`ch+0` bit 3) |
| `$86` | `$180bc` | 0 | pitch slide **up** (`ch+0` bits 7+3) |
| `$87` | `$1801e` | 0 | **advance to next pattern in the sequence** |
| `$88` | `$180ca` | 2 | portamento step `ch+42`, target `ch+41`/`ch+43` |
| `$89` | `$180b0` | 1 | global transpose → `a3+2264` |
| `$8a` | `$18064` | 0 | noise: mask `$38`, `ch+1 := 0` |
| `$8b` | `$18044` | 0 | noise: mask `$07`, `ch+1 := $ff` |
| `$8c` | `$18084` | 0 | noise off, `ch+1 := $ff` |
| `$8d` | `$180e4` | 0 | alias of `$83` |
| `$8e` | `$18014` | 0 | **END OF SONG** (`addq #4,sp`; `a3+2263 := 0`; jump to stub+28) |
| `$8f` | `$180f2` | 0 | set `ch+0` bit 5 (envelope run) |
| `$90` | `$180fa` | 0 | yield channel to SFX (`ch+45 := $ff`) |
| `$91` | `$18100` | 0 | stop yielding (`ch+45 := 0`) |
| `$92` | `$180b6` | 1 | detune → `ch+46` |
| `$93` | `$18002` | 2 | set sequence-table pointer (`ch+6/+7`), index := 0 |
| `$94` | `$17ff4` | 1 | set song speed (`a3+2252`, and copy to `+2253`) |
| `$95` | `$17fe6` | 1 | set fade rate (`a3+2265`) |
| `$96` | `$17fde` | 1 | set master volume (`a3+2251`) |
| `$97` | `$17fd4` | 1 | **trigger SFX** — `moveb (a1)+,d0 / bsr $17b14` |

**Format validation.** A parser built from the table above was run over all 106
patterns reachable from all 17 songs (all three channels, all sequence entries):
**zero out-of-range opcodes**, and the highest byte consumed is `$1a489` — one byte
below `$1a48a`, where `snd_trigger_effect`'s code begins. The pattern region and the
next code region abut exactly. That is a strong end-to-end confirmation of the whole
decoding.

Opcode census across the real data: `$80`×653, `$8f`×88, `$87`×92, `$8a`×51, `$88`×48,
`$92`×16, `$8e`×11, `$89`×5, `$81`×4, `$93`×3, `$82`×2. Arpeggio: only `$cf`, twice.
Instruments: `$d0..$de` (15 of the 16 used). **Opcode `$97` is never used** — see §8.

### Sequences
`ch+6` is a word offset (a3-relative) to a table of word pattern-offsets;
`ch+10` is the byte index into it, starting at 2 (entry 0 having been pre-loaded).
`$1801e` walks it and, on a `0000` terminator, **restarts at entry 0** — so every song
loops forever unless a pattern executes `$8e`. Sequence lengths (ch0, ch1, ch2):
```
 0 [1,1,9]   1 [1,1,1]   2 [2,2,2]   3 [4,24,4]  4 [1,1,1]  5 [1,1,1]
 6 [1,1,1]   7 [4,4,10]  8 [3,3,3]   9 [3,3,3]  10 [9,9,9] 11 [8,8,1]
12 [1,1,1]  13 [3,3,3]  14 [11,11,10] 15 [1,1,1] 16 [1,1,1]
```

### Per-channel state

**Yes, the trigger/init copy pointers into per-channel state, and there are 3 channels
of each kind** (music and SFX are separate state blocks).

Music channel struct — 48 bytes (`adda.w #$30,a1` at `$17ba0`), at `$17bc6` (A),
`$17bf6` (B), `$17c26` (C):

| Off | Sz | Role |
|---|---|---|
| +0 | b | flags: b1 (`$83`), b2 vibrato, b3 slide, b5 envelope running, b7 slide up |
| +1 | b | "noise tracks note" flag (`$8b`/`$8c` set, `$8a` clears) |
| +2 | l | current pattern read pointer |
| +6 | w | sequence-table offset (a3-relative) |
| +10 | w | byte index into the sequence table |
| +14 | w | vibrato accumulator |
| +16 | l | arpeggio stream base (loop point) |
| +20 | l | arpeggio stream current pointer |
| +24 | b | vibrato depth |
| +25 | b | vibrato speed |
| +26 | b | envelope speed (byte preceding the instrument data) |
| +27 | b | note duration countdown |
| +28 | b | note duration reload |
| +29 | b | current note |
| +30 | b | current volume out |
| +31 | b | envelope speed countdown |
| +32 | l | envelope current pointer |
| +36 | l | envelope base pointer |
| +40 | b | last envelope value |
| +41/+42/+43 | b | portamento limit ×2 / step / current |
| +44 | b | portamento control (`$40` = enabled; b5 = limit reached) |
| +45 | b | yield-to-SFX flag (b7 = actually yielded) |
| +46 | b | detune |
| +47 | b | **constant** mixer mask: `$09` (A), `$12` (B), `$24` (C) |

Confirmed against the image bytes at `$17bc6`: `…+26=04 +27=04 +28=04 +29=32 …+44=60
+45=00 +46=00 +47=09`, and `+6 = $1180` = song 0's ch-A sequence offset from the song
directory.

SFX channel struct — 26 bytes (`$1aa96 - $1aa7c = $1a`), at `$1aa7c` (A), `$1aa96` (B),
`$1aab0` (C). Bytes 0..13 are the verbatim descriptor copy; 14..25 are runtime:
`+14` period-step countdown, `+15` volume-step countdown, `+16` secondary counter,
`+18` volume-stream loop base (long), `+22` volume-stream current pointer (long).

Volume streams are byte sequences: values `$00..$7f` are volumes; `$80` means "loop to
`+18`"; any other negative byte ends/holds (`$1a6a4..$1a6b0`).

### Globals (`$17c56..$17c71`, addressed `a3+2250..a3+2277`)

| Addr | a3 off | Role |
|---|---|---|
| `$17c56` | 2250 | **engine enabled / "playing"** — also polled externally as `378(stub)` |
| `$17c57` | 2251 | master volume 0..15 |
| `$17c58` | 2252 | song speed |
| `$17c59` | 2253 | song speed copy |
| `$17c5a..5d` | 2254..2257 | SFX active flags A/B/C (+pad); tested as a long at `$17ca6` |
| `$17c5e..61` | 2258..2261 | per-channel "PSG channel locked, don't write" (+pad) |
| `$17c63` | 2263 | song loaded and not ended |
| `$17c64` | 2264 | global transpose (op `$89`) |
| `$17c65` | 2265 | fade rate (0 = none) |
| `$17c66` | 2266 | fade countdown |
| `$17c68/69` | 2268 | word scratch (12-bit tone period being split) |
| `$17c6a` | 2270 | song-speed accumulator |
| `$17c6b` | 2271 | noise period base |
| `$17c6c` | 2272 | noise period out |
| `$17c6d` | 2273 | noise-channel routing mask |
| `$17c6e` | 2274 | **VBL tick-drop value (0 / `$2b` / `$48`)** |
| `$17c6f` | 2275 | tick-drop accumulator |

**The image on disk contains live residue**, not a clean initial state: `$17bc6+2` holds
`$0002e577`, `$17bc6+6` holds `$1180` (song 0), and `$1aa7c` holds a copy of SFX
descriptor 9. The absolute pointers correspond to a load base of ~`$2d360`, i.e. the
binary was saved after a run at a different address. An extractor must therefore call
stub+0 (or restore the mutable ranges) and must never trust the image values.

---

## 7. OTHER HARDWARE / OS DEPENDENCIES

**The entire external surface is: 32 PSG accesses + 1 read of `$00FFFA01` + 1 read of
`$00FF820A`.** Nothing else. Specifically:

* **No interrupt installation.** No write to any exception vector anywhere in
  `$17adc..$1abc8`; the byte-scan for hardware-address constants found only the four
  above. The driver is purely *called* — `vbl_handler` (`$716`) does
  `lea $17adc.l,a0 / jsr 14(a0)` at `$720..$726`, and per `names.txt` that VBL is the
  program's only periodic tick (MFP timers A and B are masked off at boot).
* **No MFP timer programming**, no Timer-A/B/C/D setup, no `$fffa1x` writes.
* **No OS calls** — no `trap #1/#13/#14`, no GEMDOS/BIOS/XBIOS, no reads of OS
  variables (`_hz_200`, `frclock`, `_sysbase`, …).
* **Supervisor mode required.** `$17e34` and `$17f30` do `move.w %sr,Dn` /
  `move.w #$2700,%sr` / restore — privileged. Interrupts are masked to level 7 only
  around the PSG I/O windows.
* **Self-modifying data.** All state lives inside the code image (`$17bc6`, `$17c56`,
  `$18352`, `$18360`, `$1aa7c`, `$1aae6`), so the module needs a writable text segment
  and is not re-entrant or shareable.
* **Fully PC-relative.** Every routine begins `lea $1738c(pc),a3` and every internal
  reference is `(pc)` or `d16(a3)` / `(a3,Xn.w)`. Only the *callers* use an absolute
  `lea $17adc.l`. The module is therefore relocatable as a blob.
* **Stateful PRNG** at `$1aae6` (`$1aaca` rotates a 32-bit value through X), consumed by
  SFX whose descriptor `+7` is non-zero (sfx 12, 20, 21). It is *not* reset by init, so
  SFX pitch noise is history-dependent.

---

## 8. IDENTIFICATION

**No strings, no signature, no author credit.** An ASCII scan of `$17adc..$1abd0`
returns only false positives — pattern note bytes in `$20..$7e` rendering as text
(e.g. `$0186a7 "@ELHJLHE@ELHJLHE"` is a melody line, note numbers `$40 $45 $4c $48 …`).
A whole-image string scan finds no music/driver credit at all; the only joke strings are
game text (`"Wheres Saigon??????"`, `"If you keep running out… Psygnosis!!"`) and the
`.RAD` filename table at `$21439`.

There is **no SNDH header** (the module is linked into the game binary, not a standalone
tune file) and no recognisable public-driver marker.

Assessment: this is a **custom in-house driver**, not a recognisable public ST replayer.
Distinguishing traits, none of which match Soundmonitor / TCB Tracker / Music-Mon /
MaxYMiser:

* Entry via a table of `movem`-wrapped thunks with *per-entry* register masks
  (`$fffe`, `$0010`, `$6000`) — an unusual, hand-tuned touch.
* Single base register `a3` with **16-bit a3-relative offsets** used for *all* pointers,
  including the pointer tables themselves (`word + a3`), so the whole module is
  position-independent in a 64 K window.
* Opcode encoding split by *range* rather than a nibble: `$00-$7f` note, `$80-$97`
  command, `$c0-$cf` arpeggio, `$d0-$df` instrument, `$e0-$ff` duration — decoded by
  a chain of `addi.b` + `bcs` (`$181ac..$181b8`) rather than a mask.
* SFX as a *separate* engine with its own 3-channel state, its own 14-byte descriptor
  format, its own volume streams and its own PRNG, mixed into the music via
  per-channel "lock" and "yield" flags.
* 96-note equal-tempered table (8 full octaves) — larger than most ST drivers ship.

The family resemblance (thunk table, base-register-relative data, `$e0+n` duration
encoding, separate SFX engine) is closest to the "coder's own driver shipped with the
port" pattern typical of late-80s Images Software / Activision ST conversions.

### One latent defect worth recording

Opcode `$97` (trigger SFX from the music stream) is:
```
17fd4: moveb %a1@+,%d0     ; SFX id
17fd6: bsrw  0x17b14       ; stub+56 -> snd_trigger_effect
17fda: braw  0x18116
```
It sets `d0` but **never sets `d1`**, and `$1a48a` dispatches on `d1` to choose the
channel. At that point `d1` holds whatever the SFX tick (`$1a5da`, called earlier in
the same `snd_music_tick`) happened to leave in it — e.g. `$1a642` loads it from a
descriptor field. So the channel would be effectively random.

This is **latent only**: the pattern walk over all 106 patterns of all 17 songs found
**zero occurrences of `$97`**. Do not "fix" it in a port — reproduce it, or assert it is
unreachable.

---

## Extraction plan implications

### What an emulator-driven extractor must model

1. **PSG at `$FF8800` / `$FF8802`, byte access, including the `$00FF88xx` alias.**
   The operands are 32-bit absolutes `$00FF8800` / `$00FF8802`, so a model that only
   decodes `$FFFF88xx` will miss every access.
2. **PSG register read-back on `$FF8800`.** Exactly two sites (`$17f08`, `$17f3e`),
   both after selecting register 7. Return the latched value of register 7. Returning 0
   is *not* benign: it clears mixer bits 6/7 (the port A/B direction bits that the FDC
   driver at `$624c` depends on) and corrupts the channel-ownership merge.
3. **`$00FFFA01` bit 7 and `$00FF820A` bit 1** — the tempo selector. See below.
4. **Supervisor mode + a writable text segment.** The module executes
   `move.w #$2700,%sr` and keeps all of its state inside the loaded image.
5. **Nothing else.** No interrupts to install, no timers to run, no OS to emulate. Drive
   the tick yourself; the module never asks for time.

### Forcing the 50 Hz path

```
read $00FFFA01  ->  any byte with bit 7 SET   (e.g. $80, or the real-ST idle $B9/$F9)
read $00FF820A  ->  any byte with bit 1 SET   (i.e. $02)
```
Then `$17c6e` stays 0, no ticks are dropped, and one call to stub+14 per emulated frame
is exactly one 50 Hz music tick. With both reads returning 0 the driver picks the
**mono** value `$48` and silently drops 28% of ticks.

### Exact call sequence to play song N

```
; one-time
load SWB.PRG image (text at base B); stub = B + ($17adc - $3f8)
enter supervisor mode
install the two hardware-read values above

; start
d0.w = N                    ; 0..16
jsr  0(stub)                ; -> $17b3a : stops, resets 3 channels, volume 15, enabled

; per frame, at 50 Hz
jsr  14(stub)               ; -> $17c74 : music + SFX + PSG output
                            ;    capture PSG writes here for a register-log dump

; end detection
tst.b 378(stub)             ; = $17c56 ; zero => the song executed opcode $8e (or faded out)
                            ; NOTE: most songs loop forever (sequence terminator restarts
                            ; at entry 0); only 11 `$8e` opcodes exist in the whole data set,
                            ; so bound the capture by frame count as well.

; optional
jsr  84(stub)               ; fade out (rate 10), engine self-stops when volume hits 0
jsr  28(stub)               ; stop / silence   (resumable)
jsr  42(stub)               ; resume
d0.w = id (0..25); d1.w = ch (0=A, 1=B, else C)
jsr  56(stub)               ; trigger SFX
```

**Reset between songs by reloading a pristine image.** Stub+0 resets the music channels,
the globals and (via +28 → `$1aaea`) the SFX active flags, but it does **not** reset the
PRNG at `$1aae6` nor the SFX channel blocks at `$1aa7c`, and the image as shipped
already contains residue from a previous run. Reload, or snapshot and restore
`$17bc6..$17c71`, `$18352..$1836a`, `$1aa7c..$1aac9`, `$1aae6..$1aae9`.

### Static extraction (no emulator) is also viable

Every format is fully decoded and validated above: 17 songs, 26 SFX, 96-note period
table, 16 instruments, 16 arpeggios, 24 opcodes, 106 patterns, and the pattern region
ends exactly where the next code region begins. A pure-Python renderer is feasible; the
emulator route is still the better *oracle* for a differential.

### Relocatability

The module is 100% PC-relative. To lift it, copy `$17adc..$1abc8` (4333 bytes) to any
address `X` and have callers use `X` as the stub base; the internal
`lea $1738c(pc),a3` will resolve to `X - $750`. No data below `a3 + $0c48` is ever read,
so the `$750` bytes preceding the blob need to exist as address space but need not be
copied.
