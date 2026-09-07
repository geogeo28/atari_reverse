# Flying Shark — the sound module (`A\MODULE.BAK`)

Everything the game plays goes through this one 4 KB file. `$ff8800`/`$ff8802` appear **nowhere
else** in `FLYSHARK.PRG` (grep `out/prg_dis.txt`), so the module's tables *are* the game's music
and its sound effects, and its four entry points are the whole audio API.

Sources: `out/module_dis.txt` (`prg_dis.py --base 0x58944`), `out/module_decomp.c`
(`ghidra_proj_module`), and the caller sites in `out/prg_dis.txt`.

## Where it lives, and the base-address correction

`MODULE.BAK` is a GEMDOS `.PRG`: `601a`, text `0x1048`, no data, no bss, `ABSFLAG = 0xffff`, no
relocation table — i.e. genuinely position-independent, every reference inside it is PC-relative or
relative to a base register.

The file table entry at `0x16304` reads **the whole file, header included** (`len 0x1065`) to image
`+0x48928` = Ghidra **`0x58928`**. The game then calls it with

```
41f900048944   lea $58944.l,a0     ; 14 sites in prg_dis.txt
4ea80026       jsr 38(a0)
```

`0x58944 = 0x58928 + 28`. **The loader does not strip the header; the game adds 28 itself.** So the
module's TEXT base — and the value of `a3` inside every routine — is `0x58944`, not `0x58928`.
`0x5896a` (`0x58944 + 38`) is `48e7 e0f0` = `movem.l d0-d2/a0-a3,-(a7)`, which is the confirmation:
at base `0x58928` offset 38 would land mid-word. The Ghidra project and `out/module_dis.txt` both
use `0x58944`; `out/module_text.bin` is the header-stripped TEXT.

Everything below is quoted as `module_base + offset`, with `module_base = 0x58944`.

## The ABI

Four entries, all reached as `jsr n(a0)` with `a0 = module_base`.

| off | address | name | in | out | clobbers | memory |
|-----|---------|------|----|-----|----------|--------|
| +38 (0x26) | `0x5896a` | `sound_vbl_tick` | — | — | none (saves `d0-d2/a0-a3`) | reads `$ff820a`; writes `$ff8800`/`$ff8802`; reads+writes `module_base+0x00..0x25` and the three channel structs |
| +434 (0x1b2) | `0x58af6` | `sound_stop` | — | — | none (saves `a0`) | writes `module_base+0x07..0x09` (volumes) and `+0x1e` (`music_active`) |
| +1196 (0x4ac) | `0x58df0` | `sfx_start` | `d0.b` = sfx 0..12 | — | none (saves `d0/a0/a1`) | reads `sfx_table`; writes `module_base+0x0a..0x1f` |
| +1256 (0x4e8) | `0x58e2c` | `music_start` | `d0.b` = tune 0..4 | — | none (saves `d0-d2/a0/a1`) | reads `tune_table`; writes `module_base+0x1e..0x22` and all three channel structs |

Every entry saves and restores what it uses, so from the caller's point of view all four are
register-transparent. `sound_stop` ignores `d0` (the game loads one at `0x1219c` anyway).

There is **no init entry**: the module's variable block ships zeroed except `+0x25 = 0x0f`
(`master_volume`), and `music_start`/`sfx_start` seed everything else. A capture harness therefore
only has to load the file, point `a3`/`a0` at `file+28`, and start calling.

**Detecting the end of a track.** `module_base + 0x1e` (`music_active`) is non-zero from
`music_start` until either `sound_stop` or pattern command `0x88` (end of song) clears it. The game
itself polls exactly this byte, at `0x10574` (wait for the level-start jingle) and at `0x125aa`
(restart the level theme when it has run out). `module_base + 0x1f` (`sfx_active`) is the same
signal for effects and is polled at `0x12944` and `0x13e3c`. A **loop** is invisible in those flags —
a sequence list ends with a `0x0000` word which restarts the list at index 0, so a looping tune
never clears `music_active`; to detect a loop, watch a channel's sequence cursor
(`channel + 0x01`) wrapping back to 0.

## The variable block, `module_base + 0x00 .. 0x25`

`+0x00 .. +0x0c` is the **PSG register shadow**, written out by the tail of every tick in this order
(register number → shadow byte):

| PSG reg | shadow | meaning |
|---|---|---|
| 1, 0 | `+0x00`, `+0x01` | channel A period, stored as one big-endian word (coarse first) |
| 3, 2 | `+0x02`, `+0x03` | channel B period |
| 5, 4 | `+0x04`, `+0x05` | channel C period |
| 6 | `+0x06` | noise period |
| 7 | (computed) | mixer, see below |
| 8, 9, 10 | `+0x07`, `+0x08`, `+0x09` | volumes A, B, C |
| 12, 11 | `+0x0a`, `+0x0b` | envelope period (coarse first) |
| 13 | `+0x0c` | envelope shape — **only written when non-zero, then zeroed**: a one-shot latch |

The mixer byte starts at `0xf8` (three tones on, no noise, both ports input) and is EOR'd with
`0x09` / `0x12` / `0x24` when the corresponding channel's out-flag byte (`channel + 0x14`) has bit 0
set, which swaps that channel from tone to noise.

The rest:

| off | name | role |
|---|---|---|
| `+0x0d` | `sfx_duration` | counts down per tick; at 0 zeroes volume C and clears `sfx_active` |
| `+0x0e` | `sfx_period_delta` | signed word added to `sfx_period_current` every tick |
| `+0x10` | `sfx_period_reset` | value snapped back to when the reset counter fires |
| `+0x12`, `+0x14` | `sfx_period_alt_delta` | a longword holding two alternative deltas |
| `+0x16` | `sfx_period_current` | the running channel-C period |
| `+0x18`, `+0x19` | reset / alternation reloads | 0 in `+0x18` disables the reset entirely |
| `+0x1a` | `sfx_alt_pattern` | rotated right 1 bit per alternation; carry picks delta A or B |
| `+0x1b` | `sfx_noise_pattern` | rotated right 1 bit per tick; carry switches channel C to noise |
| `+0x1c`, `+0x1d` | the two countdowns | |
| `+0x1e` | `music_active` | see above |
| `+0x1f` | `sfx_active` | see above |
| `+0x20` | `vbl_50hz_divider` | 60 Hz only: counts 6→1 and skips one tick in six |
| `+0x21`, `+0x22` | tempo reload / counter | reload comes from the tune record |
| `+0x23` | `noise_period_default` | written to shadow `+0x06` at the top of every music update; set by a noise note |
| `+0x24` | `noise_period_alt` | set by pattern command `0x8b`, used by the alternating-noise flags |
| `+0x25` | `master_volume` | ships `0x0f`; a global attenuation the game never writes |

## The tick, step by step (`0x5896a`)

1. `clr.w d0`, `a3 = module_base`.
2. If `music_active` is clear, skip to 5.
3. **50 Hz normalisation.** `btst #1,$ff820a`: bit 1 set = 50 Hz, so the tick runs. Clear = 60 Hz,
   and `vbl_50hz_divider` counts 6,5,4,3,2,1 — the tick that reloads it to 6 returns early. Five
   ticks in six at 60 Hz is 50 sequencer steps per second, matching a 50 Hz machine exactly.
4. **Tempo.** `music_tempo_counter--`; at zero it is reloaded from `music_tempo_reload` and
   `channel_sequencer_step` runs for A, B and C. Then, *every* tick, `noise_period_default` is
   copied to the noise shadow and `channel_frame_update` runs for the three channels, writing the
   three volume shadow bytes and the three period words.
5. **Sound effect.** If `sfx_active`: age `sfx_duration`; step the alternation counter and add the
   selected alternate delta to `sfx_period_current`; add the constant delta; run the reset counter;
   then force channel C to volume `0x10` (hardware-envelope mode), period `sfx_period_current`, and
   noise on/off from the next bit of `sfx_noise_pattern`. **This overwrites whatever the music just
   put on channel C** — effects pre-empt the music there and nowhere else.
6. Build the mixer byte and write the 14 shadow bytes to the PSG.

## The music format

`music_start(n)` reads `tune_table + n*8` (`0x58e84`, five records):

```
tune 0  tempo 4   seq A 0x5b0  B 0x5e0  C 0x5ea
tune 1  tempo 4   seq A 0x5fc  B 0x650  C 0x670
tune 2  tempo 3   seq A 0x6a0  B 0x6b4  C 0x6be
tune 3  tempo 5   seq A 0x6c4  B 0x75c  C 0x782
tune 4  tempo 5   seq A 0x7a8  B 0x7b2  C 0x7c2
```

**Five tunes, three channels each.** A *sequence list* is a run of words (each a pattern offset from
`module_base`) ended by `0x0000`, which restarts the list — that is the loop. Tune 4's channel-A
list has no terminator before channel B's begins; it is a one-shot jingle that ends with pattern
command `0x88` instead.

A *pattern* is a byte stream:

| byte | meaning |
|---|---|
| `0x00`–`0x53` | tone note; index into `note_period_table` (84 entries, exactly this range) |
| `0x54`–`0x7f` | noise note; sets out-flag bit 1 and writes `byte - 0x54` to `noise_period_default` |
| `0x80`–`0x8c` | command, dispatched through the 13-word table at `0x58c22` |
| `0xb0`–`0xb5` | set the arpeggio loop point from the 6-byte table at `0x58c3c` (`00 01 03 05 07 00`) |
| `0xc0`–`0xdd` | select instrument `byte - 0xc0` (14 exist) |
| `0xe0`–`0xff` | set note length to `byte - 0xe0 + 1` sequencer steps |

Only a note byte and command `0x80` (rest) end a step; every other command is consumed and parsing
continues, so a note is preceded by however many parameter bytes it needs. The commands:

| cmd | routine | effect |
|---|---|---|
| `0x80` | `0x58bdc` | rest — envelope byte `0xf0` for one note length |
| `0x81` | `0x58b64` | clear all channel flags |
| `0x82` | `0x58b36` | pitch slide, 2 operands: step (signed), delay |
| `0x83` | `0x58b5a` | portamento down (note decremented per frame) |
| `0x84` | `0x58b5e` | portamento up |
| `0x85` | `0x58b0a` | end of pattern → advance the sequence list |
| `0x86` | `0x58b44` | vibrato, 2 operands: speed, depth |
| `0x87` | `0x58b70` | alternating noise on |
| `0x88` | `0x58af0` | **end of song** — silences and clears `music_active` |
| `0x89` | `0x58b30` | transpose, 1 operand |
| `0x8a` | `0x58b6c` | alternating noise, one shot |
| `0x8b` | `0x58b68` | set noise period, 1 operand, then as `0x8a` |
| `0x8c` | `0x58b2a` | tie (note = `0xff`, so the next note keeps the envelope) |

A new sequencer step clears the flag byte except bits 4 and 5 (`andi.b #$30,(a0)`), so vibrato
survives a note change and everything else does not.

**Instruments.** `channel + 0x0f` selects one of 14; `instrument_envelope_offsets` (`0x58cc8`,
14 bytes) gives its byte offset inside `volume_envelope_table` (`0x5911f`). Each envelope byte is
*high nibble = frames to hold, low nibble = PSG volume*; the tick subtracts `0x10` per frame and a
borrow fetches the next byte. `>= 0xf0` means finished (silent). The volume finally written is
`(level | 0xf0) + 1 + master_volume`, kept only if that carried — with `master_volume = 0x0f` every
level passes through unchanged, and a lower value clips the quiet steps to silence.

**Arpeggio.** `arp_sequence_table` (`0x59115`, 10 bytes `52 80 00 83 00 84 00 87 00 8c`) is walked
by `channel + 0x16`; a byte with bit 7 set is the last of the run and snaps the cursor back to the
loop point `channel + 0x15`. The value is added to the note before the period lookup.

**Channel struct**, 24 bytes, three of them at `0x58eac` / `0x58ec4` / `0x58edc`
(`module_base + 0x568/0x580/0x598`): see the field list in `out/names_module.txt`.

## The sound-effect format

`sfx_start(n)` reads `sfx_table + n*18` (`0x598a2`). `0xf5e + 13*18 = 0x1048` = exactly the end of
TEXT, so there are **13 effects, 0..12**. The nine words are:

```
w0 period delta per tick      -> +0x0e
w1 period reset value         -> +0x10
w2 alternate delta A          -> +0x12
w3 alternate delta B          -> +0x14
w4 starting period            -> +0x16
w5 hi: reset reload  lo: alternation reload  -> +0x18/+0x19
w6 hi: alternate bit pattern  lo: noise bit pattern -> +0x1a/+0x1b
w7 hardware envelope period   -> +0x0a
w8 hi: envelope shape (PSG r13)  lo: duration in ticks -> +0x0c/+0x0d
```

The shipped table:

```
 0  0000 012c 0000 0000 012c 0000 0000 0190 0904
 1  0000 0050 0016 ffea 0050 0001 5500 1b58 0907
 2  ffe8 0168 0016 ffea 0168 0001 5500 1f40 090a
 3  0000 00c8 ffb0 0050 00c8 0002 5500 1f40 090f
 4  fffc 00c8 ffb0 0050 00c8 0001 5500 1f40 090f
 5  0040 01e0 fffc 0002 0212 0001 5500 1b58 0907
 6  0001 0010 0000 ffff 000f 0e01 55ff 1f40 091c
 7  0001 0010 0000 ffff 000f 1001 55ff 2ee0 0930
 8  fff9 0016 0002 fffe 0016 0e01 55ff 2710 0932
 9  fffe 0000 0000 0000 0000 1000 00ff 3a98 0940
10  0004 0000 0002 fffe 0000 1401 abff 4268 0950
11  0002 0013 0000 0000 0013 0000 00ff 03e8 0904
12  00dc 0258 00c8 ff38 0258 0001 5500 03e8 0904
```

All 13 use envelope shape `0x09` (single decaying ramp) and differ in period sweep, noise pattern
and duration — `0xff` in the noise-pattern byte (6..10) is noise on every tick, `0x55` (1..5, 12) is
noise on alternate ticks, `0x00` (0, 11) is pure tone.

## Which game event plays what

`out/prg_dis.txt`, the `jsr n(a0)` sites and the wrappers around them:

| game routine | call | note |
|---|---|---|
| `0x11636` | `jsr 38(a0)` | the VBL handler; the only tick site |
| `0x1217a` | `sfx_start(6)` | wrapper `sfx_play_6` |
| `0x121b6` | `sfx_start(10)` | wrapper, called from `0x10c98`, `0x11014`, and jumped to from `0x12176` |
| `0x121ce` | `sfx_start(5)` | the most-called wrapper — 10 call sites |
| `0x121e6` | `sfx_start(2)` | 5 call sites |
| `0x1293a` | `sfx_start(5)` | inline, guarded by `tst.b 31(a0)` (do not cut a running effect) |
| `0x13e32` | `sfx_start(11)` | inline, same guard |
| `0x12192` | `sound_stop` | then clears `music_active` itself |
| `0x1054e` | `music_start(4)` | the level-start jingle; the loop at `0x1054a` restarts it while `music_active` is 0 |
| `0x124f8` | `music_start(0)` | armed when the level progress counter passes `level_table[+0]` — the boss theme |
| `0x125b0` | `music_start(0x1776e)` | the per-level theme, taken from `level_table[+4]`: L1→1, L2→3, L3→2, L4→1, L5→2 |

So all five tunes and (at least) effects 2, 5, 6, 10 and 11 are reachable from the wrappers; the
remaining effects are triggered from call sites the gameplay slice will name. Tune 0 is the boss
theme, tune 4 the level-start jingle, tunes 1–3 the stage themes.

## For the capture tool

* Load `MODULE.BAK` whole at some address `F`; the module base is `F + 28`.
* Call `music_start` / `sfx_start` with the number in `d0.b`, then `sound_vbl_tick` once per frame.
* `$ff820a` must be readable — bit 1 decides the 50/60 Hz divider, and getting it wrong changes the
  tempo by 20 %. The Musashi oracle returns 0 for hardware reads, i.e. 60 Hz, which is *not* the
  machine the game runs on; force bit 1 or the capture will drop one tick in six.
* The observable surface is the 14 PSG writes per tick at `$ff8800`/`$ff8802`. Register 13 is only
  written on the ticks a shape is latched, so a per-tick register vector must carry "not written"
  as a distinct value from "written 0".
* Stop condition: `module_base[0x1e] == 0` for music, `module_base[0x1f] == 0` for an effect.
  A looping tune never stops — bound it by watching `channel_a[0x01]` (the sequence cursor) return
  to 0.
