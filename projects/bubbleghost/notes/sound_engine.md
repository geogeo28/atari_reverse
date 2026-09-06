# Bubble Ghost — the sound engine

Everything here was read out of the run-time image in `ghidra_proj` (`bin/GHOST_RT.PRG`,
load base `0x10000`, so **Ghidra address = run-time address = the `DAT_` number**) and out of
`out/prg_dis.txt`. Addresses in **bold** are the provenance: "pinned by the ISR read at
`0x14662`" means that instruction is what proves the field's offset and width.

The engine is a **three-voice software ADSR + LFO synthesiser for the YM2149**, ticked at
200 Hz from Timer C. It has **no sequencer and no note stream**: every sound is one
one-shot *voice record*, filled from a table of 56-word definitions by a single trigger
call. See "Is there music?" at the foot.

Read [`anchors.md`](anchors.md) first for the `a4` model and the install/remove path; this
file assumes it.

---

## 1. The pieces, and what is new here

| addr | name in `names.txt` | status |
|---|---|---|
| `0x142bc` | `sound_play` | **new** — the trigger API; fills a voice record from a definition |
| `0x144c4` | `sound_stop_voice` | **new** — hard stop: priority 0, gate 0, PSG volume 0 |
| `0x14510` | `sound_release_voice` | **new** — note-off: run the release phase now |
| `0x1455e` | `sound_voice_priority` | **new** — returns the voice's priority (0 = free) |
| `0x14576` | `sound_stop_all` | **new** — `sound_stop_voice` over voices 0..2 |
| `0x1459a` | `timer_c_sound_isr` | named; algorithm recovered below |
| `0x148ea` | `install_sound_vectors` | named; MFP EOI mode refined below |
| `0x1491c` | `remove_sound_vectors` | named |
| `0x14932` | `snd_isr_state` | **new** — the 13-byte block (+1 pad = 14) the installer fills and the ISR reads |
| `0x14940` | `psg_gate` | renamed from `psg_access`; it is `psg(reg, value, mask)` — see §6 |
| `0x14950` | `trap9_psg_handler` | named; semantics refined below |
| `0x14982` / `0x1499c` | `sound_start` / `sound_stop` | named |

Data, all in BSS and all built one `move` at a time by `init_globals` (`0x16d8e`):

| addr | name in `names.txt` | size | contents |
|---|---|---|---|
| `0x22cd0` | `snd_note_period` | 109 words | MIDI note → PSG tone period; **only `[24..108]` is reachable** (§5) |
| `0x22cda` | `snd_volume_scale` | 16 words | volume index 0..15 → 0, 18, 35, … 239, 256 |
| `0x22cfa` | `snd_mixer_and_mask` | 3 words | `0xf6 0xed 0xdb` — per-voice AND mask for PSG register 7 |
| `0x22daa` | `snd_voice` | 3 × 140 | the voice records (§3) |
| `0x1f20a` | `snd_def_level` | 36 × 112 | one definition per room, indexed by `room_number` (`0x23120`) |
| `0x201ca` | `snd_def_fx` | 11 × 112 | the fixed effect definitions, `fx0..fx10` |
| `0x21abe` | `room_candle_sfx` | 36 words, stride `0x78` | `room_table` (`0x21a4a`) offset `0x74`: which `snd_def_fx[5+n]` the candle plays, `-1` = none |
| `0x2315e` | `sound_enabled` | word | 0/1; multiplies into every trigger's volume index. Init 1 |

**`snd_note_period`, `snd_volume_scale`, `snd_mixer_and_mask` and the three voice records
are private to the engine** — the globals census (`out/globals.tsv`, rows `0x22cd0`,
`0x22cda`, `0x22cfa`, `0x22daa`, `0x22dac`, `0x22e1a`, `0x22e1c`, `0x22ea8`, `0x22ec2`,
`0x22f34`) shows no function outside `0x142bc..0x149b4` touching any of them.

**"Level" and "room" are the same index.** This slice was read as a per-*level* engine; the
gameplay slice reads the same word `0x23120` as `room_number`, 0..35. `names.txt` keeps
`snd_def_level` for the table (it is one definition per room, and the table name has stuck) and
`room_number` for the index. Read `snd_def_level[room_number]` everywhere below.

The **only** hardware the engine names is `$ffff8800/8802` (PSG) and `$fffffa17` (MFP vector
register). PSG registers **11, 12 and 13 are never written**: the YM's hardware envelope is
unused and every volume byte is a plain 0..15 level with bit 4 clear.

---

## 2. Install / remove, and the two things the installer changes about the machine

`sound_start` (`0x14982`) = `Supexec(install_sound_vectors)` then `sound_stop_all`.
`sound_stop` (`0x1499c`) = `sound_stop_all` then `Supexec(remove_sound_vectors)`.

`install_sound_vectors` fills the 13-byte block at `0x14932` (4 + 4 + 4 + 1 bytes written,
+1 pad byte = 14; the linear listing shows it as seven `nop`s — it is data):

| addr | width | contents | pinned by |
|---|---|---|---|
| `0x14932` | long | TOS's own `$114` Timer C vector | `move.l $114.w,(a0)+` at **`0x148ee`** |
| `0x14936` | long | `&snd_volume_scale` (`a4-8768` = `0x22cda`) | **`0x148f2`**, read into `a2` at **`0x1459e`** |
| `0x1493a` | long | `&snd_voice[2]` (`a4-8280` = `0x22ec2`) | **`0x148f8`**, read into `a0` at **`0x145a2`** |
| `0x1493e` | byte | TOS's own `$484` conterm | **`0x148fe`**, restored at **`0x148d8`** / **`0x14922`** |

Then it installs `0x14950` on `$a4` (trap #9) and `0x1459a` on `$114` (MFP channel 5 =
Timer C, 200 Hz), and writes **`$40` to `$fffffa17`** (MFP vector register).

Two consequences worth stating, because both are invisible in memory:

* **`$fffffa17 := $40` clears bit 3 = the MFP goes from software-EOI (TOS's `$48`) to
  AUTOMATIC EOI** for as long as the game's handler is installed; `remove_sound_vectors`
  puts `$48` back (**`0x14912`** / **`0x14928`**). That is what makes the ISR's IPL drop
  (next bullet) actually re-enable the MFP, since no in-service bit is left latched.
* **The ISR runs at IPL 5, below the level-6 MFP** — `ori.w #$500,sr` then
  `andi.w #$fdff,sr` at **`0x145b0`/`0x145b4`** takes the entry IPL of 6 to exactly 5 — so
  other MFP channels (the keyboard ACIA in particular) can nest inside it.

The ISR **chains** rather than `rte`s: it pushes the saved `$114` and `rts`s
(**`0x148e4`**), so TOS's own Timer C work still runs.

**Conterm is suppressed while anything is sounding.** The ISR unconditionally writes 0 to
`$484` on entry (**`0x145b8`**) and restores the saved byte only when all three voices'
duration counters are zero (**`0x148ca`–`0x148d8`**) — i.e. TOS's key click and bell, which
also drive the PSG, are muted for the whole time a voice is live.

---

## 3. The voice record — 140 (`0x8c`) bytes, three of them at `0x22daa`

`snd_voice[v] = 0x22daa + 140*v`, so voice 0 = `0x22daa`, voice 1 = `0x22e36`, voice 2 =
`0x22ec2`. **Voice index = PSG channel index**: the ISR builds its register numbers as
`8+v`, `2v`/`2v+1` and the mixer masks are per channel.

Stride pinned by `muls.w #$8c,dn` at **`0x142e6`**, **`0x1432e`**, **`0x144e0`**,
**`0x14528`**, **`0x14566`** and by `lea -140(a0),a0` at **`0x148c2`**.

### 3.1 Header

| off | w | role | pinned by |
|---:|---|---|---|
| `0x00` | word | **duration counter**, in 200 Hz ticks. 0 = voice idle (the ISR skips it entirely). Counted down only while `0x70 < 0`; reaching 0 is key-off; the release path re-arms it to 1 as a "silence me next tick" sentinel | `tst.w (a0)` **`0x145be`**, `subq.w #1,(a0)` **`0x1486a`**/**`0x14886`**, `move.w #$1,(a0)` **`0x14618`** |
| `0x02` | word | **base tone period** (12-bit PSG period). **Negative = this voice's tone is off** — the mixer bit is set and the whole pitch machine is disabled | `muls.w 2(a0),d0` **`0x1475c`**, `cmpi.w #$0,2(a2)` **`0x143bc`** |
| `0x04` | word | **base noise period** (5-bit). **Negative = noise off** for this channel | `add.w 4(a0),d0` **`0x1484a`**, `cmpi.w #$0,4(a2)` **`0x14440`** |
| `0x06` | word | **volume index 0..15**, the index into `snd_volume_scale`. Also written raw to the PSG volume register when there is no envelope (§4.4) | `move.w 6(a0),d0` **`0x14658`**, `move.w 6(a2),-(a7)` **`0x144a6`** |

### 3.2 Volume machine — an ADSR plus a triangle LFO

| off | w | role | pinned by |
|---:|---|---|---|
| `0x08` | word | **volume phase**: 0 idle, 1 attack, 2 decay, 3 sustain-hold, 4 release | **`0x145c4`** |
| `0x0a` | long | attack step per tick (positive); target is hard-wired `0x000f0000` | **`0x145d2`**, limit **`0x145d6`** |
| `0x0e` | long | decay step per tick (negative) | **`0x145f0`** |
| `0x12` | long | sustain level (the decay's target) | **`0x145f4`** |
| `0x16` | long | release step per tick (negative); target 0 | **`0x1460a`** |
| `0x1a` | long | volume-LFO amplitude limit; **0 = LFO off** | **`0x14620`** |
| `0x1e` | long | volume-LFO step per tick, negated at each limit | **`0x14636`**, `neg.l` **`0x14646`** |
| `0x22` | word | volume-LFO onset delay in ticks; counts down once, never reloaded | **`0x14626`**, `subq.w` **`0x1462c`** |
| `0x74` | long | **volume envelope accumulator** (16.16) | **`0x145c8`**, stored **`0x1461c`** |
| `0x78` | long | **volume LFO accumulator** | **`0x14632`**, stored **`0x1464a`** |

### 3.3 Pitch machine — a 3-segment envelope plus a two-rate LFO

| off | w | role | pinned by |
|---:|---|---|---|
| `0x24` | word | **pitch phase**: 0 idle, 1, 2, 3 hold, 4 release | **`0x14688`** |
| `0x26` | long | segment-1 step per tick (signed) | **`0x14696`** |
| `0x2a` | long | segment-1 target; the compare's direction follows the step's sign | **`0x146a0`** / **`0x146a8`** |
| `0x2e` | long | segment-2 step | **`0x146be`** |
| `0x32` | long | segment-2 target | **`0x146c8`** / **`0x146d0`** |
| `0x36` | long | release step; target 0. Its sign is flipped at key-off if it does not point back toward 0 | **`0x146e6`**, `neg.l` **`0x148a4`** |
| `0x3a` | long | pitch-LFO positive limit; **0 = LFO off** | **`0x14700`** |
| `0x3e` | long | pitch-LFO step (mutable — see below) | **`0x14712`** |
| `0x42` | long | step reloaded into `0x3e` when the *rising* accumulation carries out of 32 bits | **`0x1471e`** |
| `0x46` | long | pitch-LFO negative limit (used instead of `0x3a` while the step is negative) | **`0x1472a`** |
| `0x4a` | long | step reloaded into `0x3e` when the *falling* accumulation carries | **`0x14734`** |
| `0x4e` | word | pitch-LFO onset delay | **`0x14706`** |
| `0x7c` | long | **pitch envelope accumulator** | **`0x1468c`**, stored **`0x146fc`** |
| `0x80` | long | **pitch LFO accumulator** | **`0x14718`**, stored **`0x14744`** |

The pitch LFO is not a plain triangle: on each tick the *step* is added to the accumulator
and, **if that add carries out of 32 bits**, the step is replaced from `0x42` (going up) or
`0x4a` (going down) — a two-rate sweep. At the limit the step is negated (**`0x14740`**) as
usual. The musical intent of the reload pair is not grounded, so the names keep offset+role.

### 3.4 Noise machine — the same envelope, plus a plain triangle LFO

| off | w | role | pinned by |
|---:|---|---|---|
| `0x50` | word | **noise phase** (same 0/1/2/3/4 encoding) | **`0x14790`** |
| `0x52` | long | segment-1 step | **`0x1479e`** |
| `0x56` | long | segment-1 target | **`0x147a8`** / **`0x147b0`** |
| `0x5a` | long | segment-2 step | **`0x147c6`** |
| `0x5e` | long | segment-2 target | **`0x147d0`** / **`0x147d8`** |
| `0x62` | long | release step; target 0; sign flipped at key-off like `0x36` | **`0x147ee`**, `neg.l` **`0x148be`** |
| `0x66` | long | noise-LFO limit; **0 = off** | **`0x14808`** |
| `0x6a` | long | noise-LFO step, negated at ±limit | **`0x1481e`**, `neg.l` **`0x1482e`** |
| `0x6e` | word | noise-LFO onset delay | **`0x1480e`** |
| `0x84` | long | **noise envelope accumulator** | **`0x1478c`**, stored **`0x14804`** |
| `0x88` | long | **noise LFO accumulator** | **`0x1481a`**, stored **`0x14832`** |

### 3.5 Tail

| off | w | role | pinned by |
|---:|---|---|---|
| `0x70` | word | **gate**. Holds the `note` argument `sound_play` was given. **Negative ⇒ the duration counter runs and the sound auto-releases; ≥ 0 ⇒ the sound sustains** until `sound_release_voice`/`sound_stop_voice` | `tst.w 112(a0)` **`0x14864`**, written **`0x14392`**, forced `-1` **`0x14556`** |
| `0x72` | word | **priority**. 0 = the voice is free. A new sound is refused if its priority is lower | `cmp.w 114(a2),d0` **`0x14340`**, written **`0x14398`**, cleared **`0x144d0`**, returned **`0x1456a`** |

`0x88 + 4 = 0x8c` — the record is exactly full, no padding.

---

## 4. The ISR's per-voice algorithm, in ten steps

`timer_c_sound_isr` (`0x1459a`) saves `d0-d3/a0-a2`, points `a1` at `$ffff8800`, `a2` at
`snd_volume_scale`, `a0` at `snd_voice[2]`, drops to IPL 5, clears conterm, and runs the
following with `d2 = 2, 1, 0` (`dbf` at **`0x148c6`**, `lea -140(a0),a0` at **`0x148c2`** —
so voice 2 is serviced first and **voice 0 writes PSG register 6 last**).

1. **`if rec[0x00] == 0: next voice`** — an idle voice costs nothing (**`0x145be`**).
2. **Volume envelope.** Phase 1: `acc += 0x0a`, clamp at `0x000f0000`, phase++. Phase 2:
   `acc += 0x0e`, clamp at the sustain `0x12`, phase++. **Phase 3 stores nothing — it is the
   sustain hold.** Phase 4: `acc += 0x16`; when it passes 0, `acc = 0`, phase = 0 and the
   duration counter is set to 1 (the silence sentinel).
3. **Volume LFO.** If `0x1a != 0` and the delay `0x22` has expired, `acc(0x78) += 0x1e` and
   fold at ±`0x1a`, negating the step.
4. **Volume out**, only if `phase | high-word-of(0x1a)` is non-zero:
   `level = (snd_volume_scale[rec[0x06]] * ((env + lfo) >> 8)) >> 16`, clamped to 15, or 0
   if `env + lfo` is negative. Write PSG register `8 + v` (**`0x1467e`–`0x14684`**).
   *(`muls.w` uses the low words, so a summed accumulator ≥ `0x01000000` would alias; the
   shipped definitions stay far below that.)*
5. **Pitch envelope** — same three-segment shape as step 2, but with a target per segment and
   a compare direction chosen from the step's sign, so a segment may sweep either way.
6. **Pitch LFO** — as §3.3, with the carry-driven step reload.
7. **Period out**, only if `pitch phase | high-word-of(0x3a)` is non-zero:
   `delta = high word of (pitch_env + pitch_lfo)`, then
   `period = base(0x02) + (base * delta) >> 12` (rounded toward zero), clamped to
   `[0, 0xfff]`; write registers `2v` (low byte) and `2v+1` (high byte)
   (**`0x14752`–`0x1478c`**). The modulation is **relative** — `base * (1 + delta/4096)`.
8. **Noise envelope + noise LFO** — the same two machines again on `0x50..0x6e` / `0x84`,
   `0x88`.
9. **Noise out**, only if `noise phase | high-word-of(0x66)` is non-zero:
   `value = base(0x04) + high word of (noise_env + noise_lfo)`, floored at 0 and clamped at
   31, written to PSG register 6 (**`0x1485c`**). *(The clamp is `cmp.b #$1f` — a byte-wide
   compare on a word value, so a result of e.g. `0x90` slips past it and the chip takes the
   low 5 bits. Reproduce it; do not "fix" it.)*
10. **Key-off.** Only if `rec[0x70] < 0`: decrement the duration counter; when it reaches 0,
    clear the priority `0x72`, and — if the volume envelope is already idle — write volume 0
    and stop; otherwise decrement the counter again (to −1, so this fires once) and force all
    three phases that are running to 4 (release), flipping `0x36`/`0x62` if they do not point
    back toward zero (**`0x14864`–`0x148c0`**).

After the loop: if all three duration counters are 0, restore conterm; then restore `sr`, the
registers, and chain to TOS's Timer C handler.

---

## 5. The two little tables hidden inside the note table

`snd_note_period` is `lea -8778(a4),a0` = **`0x22cd0`**, indexed `2*note`
(**`0x143ee`–`0x143fa`**), and `sound_play` is its only reader. Before indexing it folds the
note by octaves (**`0x143c6`–`0x143ec`**):

```
if note < 0: no note at all
while note > 0x6c: note -= 12
while note < 0x18: note += 12
```

so **only slots 24..108 are ever addressed**. Those are MIDI note numbers: slot 24 holds
`0xeee` = 3822 → 2 MHz/16/3822 = **32.70 Hz = C1**, slot 60 holds `0x1de` = 478 → **261.5 Hz
= middle C**, slot 108 holds `0x1e` = 30 → C8, and every 12 slots the period halves exactly
(3822 → 1911 → 956 → 478 → 239 → 119 → 60 → 30). It is a 12-TET, MIDI-numbered table.

The 24 unreachable head slots are **not padding** — the author packed two other tables into
them:

| bytes | as note slots | actually |
|---|---|---|
| `0x22cd0..0x22cd8` | 0..4 | zero, genuinely unused |
| `0x22cda..0x22cf8` | 5..20 | **`snd_volume_scale[0..15]`** = 0, 18, 35, 52, … 239, 256 (a linear 0→256 ramp in 16 steps) |
| `0x22cfa..0x22cfe` | 21..23 | **`snd_mixer_and_mask[0..2]`** = `0xf6`, `0xed`, `0xdb` |

Both aliases are load-bearing: `install_sound_vectors` hands the ISR `0x22cda` as `a2`
(**`0x148f2`**) and `sound_play` reads `0x22cfa + 2v` for the mixer mask (**`0x14472`**).
Each mask clears exactly that channel's tone bit (`1 << v`) and noise bit (`8 << v`) and
preserves everything else, including the port-direction bits 6/7 that TOS owns.

---

## 6. The PSG gate — `psg_gate(reg, value, mask)`

`0x14940` is the user-mode stub: `d1 = 4(a7)` register, `d0 = 6(a7)` value, `d2 = 8(a7)`
mask, then `trap #9`, returning `d0`. `0x14950` is the supervisor handler; it raises to
IPL 7 (so the 200 Hz ISR cannot interleave a register-select with a data write) and:

* `reg &= 15`, select it at `$ffff8800`;
* **if `value < 0`, write nothing** — the call is a pure read (**`0x14962`**);
* **if `reg == 7`, read the mixer back and merge**: `value |= (current & mask)`
  (**`0x14966`–`0x14970`**) — the read-modify-write that keeps the other two channels' bits
  and TOS's port-direction bits;
* write `value` at `$ffff8802`, then **read the selected register back into `d0` as the
  return value** and leave register `0x0b` selected (**`0x1497a`**) so nothing is left
  pointing at the I/O ports.

All six gate call sites are inside `sound_play`/`sound_stop_voice`; the ISR writes the chip
directly. Nothing else in the 59 KB image names `$ffff8800`.

---

## 7. The trigger API

```c
short sound_play(const short *def,  /*  8(a6) */
                 short voice,       /* 12(a6)  0..2; anything else = "pick one" */
                 short volume,      /* 14(a6)  0..15, or <0 = keep the definition's */
                 short note,        /* 16(a6)  MIDI note, or <0 = one-shot, use def's period */
                 short priority);   /* 18(a6)  refuse if lower than the voice's current */
```

Body, in order (**`0x142bc`–`0x144c2`**):

1. **Voice choice.** With `voice` outside 0..2 it takes the first voice whose duration
   counter is 0, and if all three are busy it takes the **lowest-priority** voice (compare 0
   against 1, then the winner against 2; ties go to the higher index).
   **This whole path is dead in the shipped game — all 15 call sites pass a literal 0, 1 or
   2** (§8).
2. **Priority gate.** `if (priority < rec[0x72]) return -1` (**`0x14340`**).
3. `sound_stop_voice(voice)` — silence it before rebuilding the record.
4. `dur = def[0]`; **if it is 0, return without arming anything** (so a zero-duration
   definition is simply "stop that voice").
5. **Copy `def[1..55]` into `rec[0x02..0x6e]`** — 55 words, one `move.w (a3)+,(a0)` per word
   (**`0x14380`–`0x14390`**). The definition is therefore exactly the record's first
   `0x70` bytes, with `def[k]` landing at record offset `2k`.
6. `rec[0x70] = note`, `rec[0x72] = priority`, and **all six accumulators
   (`0x74 0x78 0x7c 0x80 0x84 0x88`) are zeroed** (**`0x1439e`–`0x143ba`**).
7. **Tone.** If `rec[0x02] >= 0`: mixer tone bit clear; if `note >= 0`, replace `rec[0x02]`
   with `snd_note_period[fold(note)]`; write PSG `2v`/`2v+1`. Else: mixer bit `1 << v`, and
   the pitch machine is switched off (`rec[0x3a] = 0`, `rec[0x24] = 0`).
8. **Noise.** If `rec[0x04] >= 0`: mixer noise bit clear; write PSG register 6. Else: mixer
   bit `8 << v`, and `rec[0x66] = 0`, `rec[0x50] = 0`.
9. `psg_gate(7, tone_bit | noise_bit, snd_mixer_and_mask[v])`.
10. If `volume >= 0`, `rec[0x06] = volume`.
11. **If the volume phase `rec[0x08]` is 0 there is no envelope**: set the accumulator to the
    full `0x000f0000` and write `rec[0x06]` *raw* (0..15) to PSG register `8 + v`
    (**`0x14498`–`0x144b4`**) — a constant-volume voice.
12. **`rec[0x00] = dur` last**, which is what arms the voice for the ISR (**`0x144b6`**).

Returns the voice used, or `-1` when refused on priority.

The other four entry points:

| addr | name in `names.txt` | body |
|---|---|---|
| `0x144c4` | `sound_stop_voice(v)` | `rec[0x72] = 0; rec[0x00] = 0; psg_gate(8+v, 0, ·)` |
| `0x14510` | `sound_release_voice(v)` | if the voice is live: `rec[0x00] = 1; rec[0x70] = -1` → the ISR's key-off fires on the next tick |
| `0x1455e` | `sound_voice_priority(v)` | returns `rec[0x72]`; 0 means free |
| `0x14576` | `sound_stop_all()` | `for (v = 0; v < 3; v++) sound_stop_voice(v)` |

Note that `sound_release_voice` has **no** range check on `v` beyond `0 <= v < 3` — same as
the others — and that it is the only writer of `rec[0x70]` outside `sound_play`.

---

## 8. The sound effects the game actually plays

Every trigger passes its volume as `sound_enabled * k`, where `sound_enabled` (`0x2315e`,
init 1) is toggled at `0x123ea` on ASCII `0x13` = Ctrl-S, so `k` is the effect's nominal volume
index and 0 mutes everything. That toggle is **not** in a menu handler: `0x12322` is
`game_frame_update`, the per-frame play-loop update, and its non-blocking `Crawio(0xff)` poll
handles `^P` (pause), `^S` (this toggle) and `^R` (abort the turn) — see
[`gameplay.md`](gameplay.md) §2.

All 15 call sites, read from the pushed arguments:

| pc | in | definition | voice | vol | note | pri | what the surrounding code is doing |
|---|---|---|---:|---:|---:|---:|---|
| `0x108b6` | `game_top_loop` | `snd_def_level[room_number]` | 0 | ×7 | −1 | 5 | room start, after `Random`/`Setpalette` |
| `0x10910` | `game_top_loop` | `fx0` | 2 | ×9 | −1 | 10 | releases voice 1, flashes colour 15 white, then counts the bonus down |
| `0x10a68` | `game_top_loop` | `fx8` | 2 | ×8 | `100 − x/4` | 10 | inside that bonus tally — a **rising pitch per 5 points** |
| `0x10b40` | `game_top_loop` | `fx1` | 2 | ×8 | −1 | 10 | the other end-of-room arm (releases voice 1 first) |
| `0x10ca2` | `game_top_loop` | `fx8` | 2 | ×8 | `100 − x/4` | 10 | the second bonus tally |
| `0x11978` | `title_menu_loop` (attract) | `snd_def_level[room_number]` | 0 | ×8 | −1 | 5 | demo playback, room start |
| `0x11a6e` | `title_menu_loop` (attract) | `fx3` | 1 | ×8 | 250 | 5 | **the blow** — sustained; the `else` arm calls `sound_release_voice(1)` |
| `0x11aa4` | `title_menu_loop` (attract) | `fx4` | 2 | ×11 | −1 | 5 | guarded on `0x22fe8 == 0` |
| `0x11bb4` | `title_menu_loop` (attract) | `snd_def_level[room_number]` | 0 | ×8 | −1 | 5 | |
| `0x11c66` | `title_menu_loop` (attract) | `snd_def_level[room_number]` | 0 | ×11 | −1 | 5 | after `show_presentation` |
| `0x11d12` | `title_menu_loop` (attract) | `snd_def_level[0]` | 0 | ×11 | −1 | 5 | with `room_number := 0` immediately before |
| `0x1270e` | `game_frame_update` | `fx4` | 2 | ×11 | −1 | 5 | same guard as `0x11aa4` |
| `0x129e2` | `ghost_blow` | `fx3` | 1 | ×8 | 250 | 5 | in-game blow, only if `sound_voice_priority(1) == 0` |
| `0x12e1e` | `ghost_blow` | `snd_def_fx[5 + room_candle_sfx[room_number]]` | 1 | ×13 | −1 | 10 | the room's candle sound, skipped when the index is −1 |
| `0x13b5a` | `room_wipe_in` | `fx2` | 0 | ×8 | 60 | 5 | releases voices 0/1/2 first; a **sustained C4** later stopped at `0x13bdc` |

**Voice convention:** voice 0 carries the per-room theme, voice 1 the blow and the room's
candle, voice 2 the event/score sounds.

**The sustain rule is visible here.** `note = −1` gives an auto-releasing one-shot; `note ≥ 0`
gives a sustained sound the caller must stop — and the two `note ≥ 0` families are exactly
the two that have an explicit stop: `fx3` released at `0x11a7c`, `fx8` hard-stopped at
`0x10aa0`/`0x10cd4`, `fx2` released at `0x13bdc`.

### 8.1 `snd_def_fx` — the 11 fixed effects at `0x201ca`

Values are the definition words already interpreted as record fields (`dur` in 200 Hz ticks,
`tone`/`noise` the base periods, `vol` the volume index).

| id | addr | dur | tone | noise | vol | shape |
|---:|---|---:|---:|---:|---:|---|
| 0 | `0x201ca` | 1400 | 1214 | off | 15 | 14-tick attack, full sustain, 340-tick release; two-segment pitch sweep under a fast pitch LFO |
| 1 | `0x2023a` | 80 | 284 | off | 15 | very fast attack, very fast release; a steep two-segment pitch drop, no LFO |
| 2 | `0x202aa` | 400 | 357 | off | 9 | attack→decay, instant release; big pitch LFO — the sustained `0x13b5a` tone |
| 3 | `0x2031a` | 212 | **off** | 28 | 3 | **noise only** — the blow/wind. Full sustain, noise envelope + noise LFO |
| 4 | `0x2038a` | 4 | 35 | off | 10 | a 20 ms tick: instant attack, instant release, huge pitch step |
| 5 | `0x203fa` | 200 | **off** | 16 | 15 | noise burst with a falling noise envelope |
| 6 | `0x2046a` | 60 | 477 | 17 | 15 | tone + noise, short |
| 7 | `0x204da` | 40 | 38 | off | 15 | very short high blip, no pitch machine at all |
| 8 | `0x2054a` | 60 | 1250 | off | 15 | the bonus-tally note: full sustain, pitch set from the caller's note |
| 9 | `0x205ba` | 40 | 4032 | off | 15 | very short low blip, no pitch machine |
| 10 | `0x2062a` | 200 | 477 | 16 | 15 | tone + noise, full sustain with a noise envelope |

**All eleven are reachable**, and the census that says so is the per-room selector: `fx5`
through `fx10` are exactly `0x203fa + 0x70*room_candle_sfx[room_number]`, and over the 36 rooms
`room_candle_sfx` takes the values `{-1, 0, 1, 2, 3, 4, 5}` — `-1` on rooms 3, 4 and 13, and
`0,1,2,3,4,5` elsewhere, so every slot 5..10 has at least one room that plays it.
`fx0..fx4` have direct call sites in the table above.

### 8.2 `snd_def_level` — one definition per room at `0x1f20a`

36 records of `0x70` bytes, `0x1f20a .. 0x201ca`, indexed by `room_number` (`0x23120`).

**36 is the room count, and three independent strides say so.** `0x1f20a + 36*0x70`
is exactly `0x201ca` = `snd_def_fx[0]`; `object_table` (`0x2069a`) has stride `0x8c` and
`0x2069a + 36*0x8c` is exactly `0x21a4a`, which `ghost_blow` (`0x129b4`) reads as the *next*
per-room array — `room_table`, stride `0x78`, with `room_candle_sfx` at its offset `0x74`;
and `0x21a4a + 36*0x78` is exactly `0x22b2a`, `candle_table`, which `ghost_blow` reads after
it. Four consecutive per-room tables, each ending exactly where the next begins. And the
selector's slot 36 reads garbage (`344`), which is the negative half of the same claim.

All 36 are pitched tones with `noise` off except slots 10 (`noise = 8`) and 11
(`noise = 10`). Volume index is 15 for slots 0..30 and 12/14 for 31..35. Durations run
140..940 ticks (0.7–4.7 s). **All 36 have a pitch LFO**, 35 also run a pitch envelope (slot 10
does not), and 29 have a volume LFO. Slots 0 and 3 are **byte-identical** and are the only
two with no volume envelope (`vphase = 0` → the constant-volume path of §7 step 11).

Full field-by-field decode: re-run the extractor sketch in §10.

---

## 9. Is there music? — **No.**

* The ISR contains **no stream pointer, no note list, no command dispatch and no tempo
  counter**. It walks three fixed records and does arithmetic; the only table it reads is
  `snd_volume_scale`.
* Nothing outside the ISR is installed on any vector, and no other function is called at a
  musical rate.
* Everything audible is a **one-shot voice record** triggered by game code: a per-room
  theme, a blow, a handful of event effects.
* The one thing that *sounds* like a melody is the bonus tally — `game_top_loop` re-triggers
  `fx8` with `note = 100 − score/4` each time it takes 5 points off, so the rising glissando
  is produced by the **frame loop**, not by a sequencer.
* The only other audio in the program is the digitised "Welcome to Bubble Ghost" speech,
  which is played synchronously by `GHOST.LOA` on MFP Timer A and has nothing to do with
  this engine (`assets_survey.md`, `loader.md`).

So: **11 fixed effects + 36 per-room tones, no music, no sequencer.**

---

## 10. Reproducing the table decode

The definitions live in BSS and are written one `move.w #imm,(a1)+` at a time by
`init_globals`, so they cannot be read out of the file — simulate the initialiser:

```python
import re, struct
A4 = 0x24f1a
lines = open('projects/bubbleghost/out/prg_dis.txt').read().splitlines()
i = next(n for n, l in enumerate(lines) if l.startswith('016d8e:'))
mem, cur = {}, None
for l in lines[i:]:
    m = re.match(r'^[0-9a-f]{6}: [0-9a-f ]+\s\s+(.*?)\s*$', l)
    if not m: continue
    op = m.group(1)
    if op == 'rts': break
    mm = re.match(r'lea (-?\d+)\(a4\),a1', op)
    if mm: cur = A4 + int(mm.group(1)); continue
    mm = re.match(r'move\.(w|l|b) #\$([0-9a-f]+),\(a1\)\+', op)
    if mm:
        sz = {'b': 1, 'w': 2, 'l': 4}[mm.group(1)]
        v = int(mm.group(2), 16)
        for k in range(sz): mem[cur + k] = (v >> (8 * (sz - 1 - k))) & 0xff
        cur += sz; continue
    mm = re.match(r'adda\.w #\$([0-9a-f]+),a1', op)
    if mm: cur += int(mm.group(1), 16); continue
    if op.startswith('move.l a0,(a1)+'): cur += 4
```

Then read `snd_def_fx[i] = 0x201ca + 0x70*i` and `snd_def_level[i] = 0x1f20a + 0x70*i` with
the offsets of §3.

---

## 11. Addresses looked at and deliberately NOT named

* `0x22cd0..0x22cd8` — the note table's five leading zero slots. No reader can reach them
  (§5); left unnamed rather than invented.
* `0x14932..0x1493f` — proposed as one `snd_isr_state` block with the field map in its
  comment, rather than four separate `var` lines, because the installer walks it with
  `(a0)+`.
* `0x2069a` — the array immediately above `snd_def_fx[10]`. It is not sound data; it is what
  bounds `snd_def_fx` at 11 entries. The gameplay slice read it and it is now
  **`object_table`**, 36 rooms × `0x8c`.
* `0x21abe` — this slice reached it only as an effect selector. It is offset `0x74` of the
  `0x78`-byte **room record** based at `room_table` (`0x21a4a`), whose other fields belong to
  the gameplay slice, and it is now **`room_candle_sfx`**: the sound the room's candle makes.
* `0x2315e` — `sound_enabled`. The *key* that toggles it (`0x123ea`, ASCII `0x13`) sits in
  `game_frame_update` (`0x12322`), the play-loop frame update, which the gameplay slice owns.
* `0x22fe8` — the guard on the two `fx4` triggers. It is the gameplay slice's
  **`bubble_frame`**; the guard `bubble_frame == 0` means "the bubble has just popped".
* `0x13b1e` — the only caller of `fx2`; it releases all three voices, plays a sustained C4
  and stops it 190 bytes later. Its overall job is now read: it is **`room_wipe_in`**, the
  40-step slide that brings the staged room down into the work buffer
  ([`gameplay.md`](gameplay.md) §7), and the sustained tone is that transition's sound.

## 12. Two corrections to what was already written down

* The voice records are at **`0x22daa`** — an earlier off-by-`0x20` reading of the same
  `lea` put them a little higher in BSS. `a4 - 8560` with `a4 = 0x24f1a` is `0x22daa`
  (`lea -8560(a4),a0` at **`0x1432c`**), and that is the address to build against. Likewise
  `a4-8448 = 0x22e1a` is record 0's **gate** field `+0x70` and `a4-8446 = 0x22e1c` its
  **priority** `+0x72` — fields of record 0, not separate tables.
* `anchors.md` says the ISR "forces `$484` to 0 while a voice is active". It clears `$484`
  **unconditionally on every tick** and restores it at the *end* of the tick only when all
  three voices are idle — which is the same net effect but a different mechanism, and the
  restore is what a reconstruction has to get right.
