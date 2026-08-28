# QA.md — BLACK ICE played headless on an emulated STE

Someone sat down and played it. Not a fixture, not a compiled-in script: a real Hatari with the
game in it, keys pressed while it ran, and a screenshot of every claim below. `bench.py` measures
the frame; this measures the *game* — does the door open, does the dog bite, does dying do
anything.

The driver is [`play_headless.py`](play_headless.py), added with this file. Everything here is
reproducible from it.

**Two binaries were tested, because the tree moved under the test.**

| | SHA-256 of `disk/BLACKICE.PRG` | what ran on it |
|---|---|---|
| build **A**, 02:11 | `90014b9bc1140f6a0bdb604d07d0797a1a32a8d8e278c5e9f2037ef45820f3ea` | every scenario below |
| build **B**, 02:43 (asm cast, joystick port 1 only, ST-Low forced) | `d5e33e2ae7ab8d5c9c0317a395cd0f9fc6ad2d8755c315f9eb672062d47b91e5` | scenarios 1 and 2, re-run |

Build B renders **exactly** the same picture as A — the two boot frames differ in **0 of 204,800
view pixels**, and only in the frame-time digits of the HUD — and it is **~25% faster**: that boot
frame reads **75 ms** against A's 98, and the same corridor frame **121 ms** against 161. Nothing
else in the table was re-run on B, and every finding below is stated against A. The two behaviour
defects that dominate the ranking (§ Defects 1 and 2) are in `main.c`'s frame loop and
`assets.c`'s member name, neither of which build B touches.

---

## The table

| # | Scenario | Verdict | Evidence | What a player sees |
|---|---|---|---|---|
| 1 | Boot → first frame | **PASS** | `s12/shots/01_boot.png`, `s1new/shots/N1_boot.png` | The corridor is there and it is clean — no garbage, no half-drawn page, no wrong-pen palette. The HUD reads `INGRESS`, a clock, a frame time, `1%` trace over a dark bar, `100%` over a green bar, `60` cycles, three token pips `A B / C` unlit, and a white weapon icon. Start pose is map cell (15.5, 28.5) facing north. |
| 2 | Walk 2 s, turn left 1 s, turn right | **PASS** | `s12/shots/02_fwd.png`, `03_walk_{0,1,2}.png`, `04_left.png`, `06_right2.png`; build B: `s1new/shots/N2_fwd.png`, `N3_walk_1.png` | Smooth. Walls converge correctly, the texture scrolls with the walk, the view rotates coherently. **No tearing and no black frames in 60+ captures** — the page flip is solid. Measured on the HUD: **75–191 ms a frame, i.e. 5.2–13.3 fps** (build B; A was 78–191). Walking is ~3.7 cells/s, turning ~115°/s as the player actually receives it. |
| 3a | Walk into the `1` gate **without** the ALPHA token | **PASS** | `s3b/shots/10_refuse_0.png` | The gate blocks and the HUD title line turns white with **`ALPHA TOKEN REQUIRED`**, held ~2 s. The gate itself renders well: teal panel, magenta hazard bands, a bright cyan pillar. |
| 3b | Pick up the ALPHA token, HUD key pip | **PARTIAL** | pickup drawn: `s3/shots/12_alcove.png`, `13_token.png`; pip lit: `s8c/shots/61_gate_1.png` | The pickup sprite is drawn beautifully — a yellow disc with a green core and a white rim. **But the token was never collected in any run**: every route to the west alcove crosses the Sentry's alcove at map x=10, and the Sentry killed the player first in 4 of 4 attempts. With the token granted by a debugger poke the pip `A` lights correctly. The *collection* itself is therefore untested. |
| 3c | Walk into the `1` gate **with** the token | **PASS** | `s8c/shots/61_gate_{1,3}.png` | It opens on contact, no button, and the player walks straight through into the Handshake Hall. |
| 4 | Meet a Watchdog / Sentry: chase, bite, shoot, dissolve | **PARTIAL / FAIL** | `s4g/shots/A0_sentry_286deg_int52.png`, `A1_kennel_{0,270}deg.png`, `A2_w26_17_int0.png`; damage: `s4e.txt`, `s4f.txt` | **They are drawn and they hurt.** With the camera aimed at one, an enemy fills the view as a magenta blob with a white rim. Integrity falls fast and visibly: 100 → 92 → 76 → 52 → 28 → 16 → 4 → 0 in the Sentry's cone over ~12 s; the four-dog kennel took 16 → 0 in ~3 s. **Shooting them never worked**: 30+ Buster shots across four runs, `kills` stayed 0 every time, nothing dissolved. Firing spends 1 cycle a shot (60 → 21 observed) and **produces no picture at all** — no flash, no recoil, nothing (§ Defects 6). The kills may be my aim (a scripted turn lands within tens of degrees), so this is reported as unproven, not as a broken weapon. |
| 5 | Trace meter over 60 s standing still; the 25% threshold | **PARTIAL** | `s5/shots/30_trace_*.png` (0–90 s), `s5b/shots/31_trace_*.png` (110–182 s) | The meter rises and reads correctly: 1% at boot, **15.1% at 60 s**, 21.8% at 90 s, and it crosses into band 1 at **25.5%, 110 s**. The number and the yellow bar both move. **Nothing else changes.** The 16 palette registers are byte-for-byte identical either side of the threshold (§ Defects 4). Music tempo could not be heard; the code does call `ym_music_set_speed` on the band change. |
| 6 | Esc exits cleanly | **PASS** | `s6b/shots/41_after_esc.png`, and from a dead run `s7/shots/54_dead_esc.png` | Straight back to the EmuTOS desktop. Palette, resolution and mouse restored, no bombs, Hatari exit status 0. Also the only way out of a dead game. |
| 7 | Integrity → 0 → death screen / retry | **FAIL** | `s7.txt`, `s7/shots/51_hit_00_int0.png`, `52_after_death.png`, `53_dead_walk.png` | Integrity reaches 0 and `GameState.phase` becomes `PHASE_DEAD`. **Then nothing happens.** No death screen, no retry, no restart. The world freezes — trace stops, enemies stop, pickups stop — but the player can still walk around inside it, and the clock keeps counting. The run is over and the program does not know it. |
| 8 | Reach the exit → level clear → level 2 loads | **FAIL** | `s8c.txt`, `s8c/shots/64_exit_0.png`, `65_after_phase2.png`, `66_after2.png` | The arch works: touching it sets `phase = PHASE_LEVEL_CLEAR`. **And that is the end of it** — no `SECTOR CLEAR` overlay, no transition, no level 2, forever. Level 2 *cannot* load: `assets.c` hard-codes `LEVEL_MEMBER_FIRST = "LEVEL1"` and nothing else ever calls `load_level`, even though `BLACKICE.PAK` ships all eight compiled levels. |
| 9 | Extra: the rest of DESIGN 6 | **MOSTLY PASS** | `s9.txt`, `s10.txt`, `s10/shots/87_p1.png`, `s9/shots/81_underclock.png` | `P` pauses (sim frozen, `PAUSED - P RESUME, ESC ABORT` on the HUD) and resumes. `7`/`8`/`9` switch throttle — the HUD dial moves and the render radius visibly changes. `Z`/`X` strafe. **`Shift`+arrow strafes; `Alt`+arrow does nothing at all** (§ Defects 5). |
| — | Joystick | **BLOCKED** | see § The joystick, below | Not the game's fault and not proven to be fine either. |

---

## The commands

Everything ran against Hatari 2.6.1 with its own bundled EmuTOS (no `--tos`: an ST ROM boots an
STE only by accident). `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`, and **no `--fast-forward`** —
real-time emulation is what makes "hold forward for two seconds" mean two seconds.

```sh
hatari --machine ste --memsize 1 --monitor rgb \
       --sound off --confirm-quit off --statusbar off --drive-led off \
       --frameskips 0 --run-vbls 400000 \
       --harddrive atari/disk --auto 'C:\BLACKICE.PRG' \
       --cmd-fifo /tmp/qa/cmd.fifo
```

and then, into that fifo while it runs:

```
hatari-event keydown 0x48          # hold Up   (ST scancode, ALWAYS spelled 0x..)
hatari-event keyup 0x48
hatari-debug screenshot /tmp/qa/frame.png
hatari-debug info basepage         # -> "Text segment : 0x01b018"
hatari-debug savebin /tmp/qa/state.bin $40758 $4224      # GameState
hatari-debug loadbin /tmp/qa/poke.bin $45adc             # one byte in
hatari-shortcut quit
```

To replay the whole thing:

```sh
cd projects/blackice/atari
python3 play_headless.py --out /tmp/qa            # boot, screenshot, print the state
# and for a scenario, drive the Session class:
python3 - <<'EOF'
from play_headless import Session, BOOT_SECONDS
s = Session("disk", "/tmp/qa/run")
s.wait(BOOT_SECONDS)
s.goto(15.5, 12.0)                 # walk to the locked gate
s.turn_to(270.0); s.down("up")     # lean on it
s.shot("refusal.png"); s.report("at the gate")
s.close()
EOF
```

**Three things the driver had to learn, all of them traps for the next person:**

* **A one-character argument to `hatari-event` is an ASCII CHARACTER, never a scancode.** Hatari's
  `Control_InsertKey` only parses a scancode when the argument has two or more characters. So
  `keydown 1` presses the `1` key, not Escape — which is why the first Escape test showed a game
  that would not quit, and why every key here is written `0x01`, `0x48`, `0x39`.
* **`savebin` takes a plain number, not an expression**, so the debugger's virtual `TEXT` variable
  cannot be added to inside the command. The driver reads the load address out of `info basepage`
  — and then does not trust the link-time offset either: `.bss` moved 8 bytes between two builds
  on the same afternoon, so `locate_state` **scans RAM for the state's boot signature** instead.
* **A held key shorter than ~0.7 s delivers one make and no repeats**, which is one frame of turn,
  about 8°. Every turn nudge is at least that long. Even so a scripted turn lands within tens of
  degrees, which is why scenario 4 had to place the camera with the debugger to photograph an enemy
  at all.

---

## The joystick — why it is still not exercised

`atari/README.md` says the joystick path has never been pressed headless. It still has not been,
and here is precisely where the wall is, so nobody re-derives it:

* The game's half is **provably correct up to the ISR**: the IKBD trace shows
  `IKBD_Cmd_TurnMouseOff` ($12) and `IKBD_Cmd_ReturnJoystickAuto` ($14) going out at boot, exactly
  as `BRIEF.md` requires, and `KBDVECS_JOYVEC_OFFSET` is 24, which is right.
* **Hatari cannot deliver a joystick press headless.** Joystick port 1 was put in keyboard mode and
  bound to `W/S/A/D/F` in a config file (verified accepted by round-tripping `--saveconfig`).
  Pressing those letters through `hatari-event` **is** intercepted by the joystick emulation — bind
  port 1's UP to `Z` and `Z` stops strafing, so the key is being swallowed — but no `$FF` packet is
  ever produced: `bi_joy_port1` and `g_joy_sticky` stay 0 through a two-second hold. Under
  `SDL_VIDEODRIVER=dummy`, `Joy_GetStickData` returns nothing for a keyboard-emulated stick.
* **What that leaves untested:** the IKBD `$FF` packet, EmuTOS's dispatch to `joyvec`, and
  `bi_joy_entry` itself. Everything *above* that byte is tested — `stick()` pokes `bi_joy_port1`
  and `joystick_input` decodes it — but the poke was only ever used to prove the read path, and no
  finding in the table rests on it.
* **The cheap way to close it** is a Hatari built with a working keyboard-joystick path under a
  headless video driver, or a real SDL joystick device. Failing that, the honest surface is a unit
  test of `bi_joy_entry` against a synthetic `$FF` packet in the Musashi harness — which would
  cover the ISR but still not EmuTOS's dispatch.

---

## Defects, ranked

**1. Death does nothing. The game becomes a zombie.** (`main.c` `play()`)
Integrity hits 0, `phase` becomes `PHASE_DEAD`, `deaths_this_sector` increments, `sim.c` pushes
`CONNECTION TERMINATED` — and `play()` never looks at `phase`. The simulation stops; the player
keeps walking through a frozen world at 0% integrity with the clock still running. The only exit is
Escape. DESIGN 18 item 7 puts death and retry in the first playable, and `game_start_level` /
`RunProgress` already exist in `src/` unused by `atari/`.
*Evidence: `s7/shots/52_after_death.png`, `53_dead_walk.png`.*

**2. Level clear does nothing, and level 2 can never load.** (`main.c` `play()`, `assets.c`)
Touching the exit arch sets `PHASE_LEVEL_CLEAR` and `next_sector_index`, and nothing consumes
either. `assets_load` opens `LEVEL_MEMBER_FIRST = "LEVEL1"` and no other code path ever loads a
level, so the eight `LEVEL*` members in `BLACKICE.PAK` are dead weight after the first. DESIGN 18
item 1 is levels 1 **and** 2.
*Evidence: `s8c/shots/65_after_phase2.png`, `66_after2.png` — twelve seconds after the arch,
still `INGRESS`.*

**3. No title screen, no SECTOR CLEAR overlay, no RUN COMPLETE.** (DESIGN 18 item 7)
`blackice_main` goes from the PAK load straight into `play()`. The `SECTOR CLEAR` *message* does
fire on the HUD's one text line for its two seconds; the overlay does not exist.
*Evidence: `s8c/shots/61_gate_4.png` has the message; there is no overlay in any frame.*

**4. The trace meter never recolours the world.** (DESIGN 18 item 5, DESIGN 9)
`set_palette` is called once, at boot. `GameState.palette_variant` is written by `trace.c` and read
by nothing on the target, and `BLACKICE.PAK` ships a single 32-byte `PALETTE` member, so the
DEGRADED and CORRUPT variants are not even on the disk. Measured: the 16 registers are identical at
1% and at 25.5%. This is half of what the trace meter is *for* — the number moves, the world does
not.
*Evidence: palette diff of `s5/shots/30_trace_00s.png` against `s5b/shots/31_trace_182s_band1.png`
— zero registers changed.*

**5. `Alt`+arrow strafe is dead on the keyboard; `Shift` works.** (DESIGN 6)
From the same standing start: `Shift`+Left strafes (x 15.50 → 12.66), plain Left turns (270° →
42°), **`Alt`+Left does nothing — position and angle both unchanged.** TOS eats Alt+arrows for its
own keyboard-mouse emulation and never puts a scancode in the buffer, so `Bconin` never sees the
arrow. DESIGN 6 names Alt first and rests "completable with joystick plus Alt" on it. `Shift` is
already implemented and already works; the fix may be as small as changing which modifier the
document promises.
*Evidence: `s10.txt`.*

**6. Firing has no feedback of any kind.** `weapons.c` sets `muzzle_flash = MUZZLE_FLASH_TICKS` and
**no code on the target ever reads it** — not the renderer, not the HUD. There is no flash, no
crosshair change, no shot tracer, and the YM cue is inaudible in this harness. The only sign that
the trigger did anything is the cycles field ticking down. Related and also absent: DESIGN 18 item
7's damage / pickup palette flash — integrity fell 100 → 0 across eight captures with no flash in
any of them.
*Evidence: `s4d/shots/73_shoot_*.png` — cycles 60 → 21 across the sequence, picture unchanged.*

**7. Nothing was ever killed.** 30+ Buster shots at a Sentry and at a four-dog pack, `kills`
stayed 0. This may be a scripted-aim artefact rather than a defect, and it is ranked here because
**QA could not confirm the game's core verb works at all.** It needs a human at the keyboard, or a
test that fires along a known bearing at a known entity.
*Evidence: `s4d.txt`, `s4f.txt`, `s4e.txt` — every `kills=0`.*

**8. The first playable is unwinnable by the route it documents.** `level1.txt`'s own note gives
the route as `@ -> Bus Hall -> west alcove (p ALPHA) -> door 1 -> Handshake Hall -> >`. The west
alcove is reachable only across the Bus Hall, and the Sentry's alcove sits at map x=10 in the
middle of that crossing with a 14-cell sight line and 8 damage a shot. Four scripted attempts, four
deaths, zero tokens. A human will be better at this than a script — but with no way to kill the
Sentry confirmed (defect 7) and no retry (defect 1), one mistake ends the session.
*Evidence: `s3.txt`, `s8b.txt`, `s4c2.txt`, `s4e.txt`.*

**9. 5–13 fps.** The HUD's own readout: 75 ms standing in the start room, 121 ms walking a
corridor, 191 ms with a near sprite in view — build B, the fast one. This is the gate
`atari/README.md` already reports as MISSED and it is stated here only as what it feels like to
play: the frame is between a fifth and a thirteenth of a second, and the input is latched once per
frame, so a tap is a coarse instrument. It is *playable* — walking and turning read as continuous —
but it is not 25 fps and never looks like it.

**10. The `PAUSED` line runs into the clock.** `PAUSE_MESSAGE` is exactly the 28 glyphs the title
bar's left half holds, so it ends flush against the clock field and reads as `ESC ABORT00:09`. One
space of gap, or 27 glyphs, fixes it.
*Evidence: `s10/shots/87_p1.png`.*

**11. Four music tempi for five trace bands.** `BLACKICE_BAND_SPEED` has 4 entries and
`TRACE_BAND_COUNT` is 5; `follow_trace_tempo` clamps, so band 4 (HARDENED) plays band 3's tempo.
DESIGN 16 asks for five distinct steps and a melody drop-out at 100%. Correctly bounded, so it is
a gap and not a bug — and inaudible in this harness.

---

## Observations that are not defects

* **The world is very dark, and it is the art, not the shader.** The corridor reads as near-flat
  navy with thin cyan seams. Measured: the shipped wall textures are **70–85% register 5**
  (`#113366`, the darkest cyan rung) before any shading. The depth remap was checked against the
  arithmetic at point-blank range and is correct (a near north-south face lands on shade level 1
  and the rendered histogram matches that level applied to texture 0 to within a percent). If the
  corridors should look brighter, that is a texture-authoring decision.
* **Black floor and ceiling are the design.** DESIGN 3 gives register 0 the role "void — floor,
  ceiling, border". It makes rooms read as slabs floating in nothing, which is a strong look and
  clearly deliberate; noted only because it is the first thing a new player will remark on.
* **Enemy sprites are placeholder-grade.** A Sentry is a flat magenta ellipse with the white rim —
  no register-13 live core, no iris. The shipped sprite sheet contains **two pixels** of register
  13 in total. The rim is present and correct, which is the part DESIGN 3's gate cares about.
* **Three token pips, not four**, is correct: `HUD_TOKEN_COUNT` is 3 and DESIGN 10 has three
  tokens.
* **The exit arch was never seen from a distance**, so DESIGN 3's "green from any distance"
  landmark claim is untested. No register 14 appeared in any view frame except the pickup.

---

## Artefacts

Screenshots, logs and per-scenario transcripts are under the session scratchpad:

```
/private/tmp/claude-501/-Volumes-Workspace-repos-my-repos-atari-reverse/\
1864b2d3-fef8-4d40-b1bf-a7281ba4ae2a/scratchpad/qa/
    frozen/   frozen2/     the two binaries under test, with SHA256.txt
    s12/ s3/ s3b/ s4*/ s5/ s5b/ s6b/ s7/ s8b/ s8c/ s9/ s10/ s1new/
                           each: hatari.log, shots/, state.bin, and the .txt transcript
```

They are session-local. Everything in them regenerates from `play_headless.py` and the snippets
above; the two SHA-256 values are what pins a re-run to the same binaries.
