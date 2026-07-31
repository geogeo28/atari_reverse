# atari/ — run the reconstructed Joust on a real 68000

This takes the reconstruction past the differential harness: it **cross-compiles the very same
verified C cores to 68000** (`m68k-elf-gcc`) and runs them as a GEMDOS `.PRG` under Hatari with a
real TOS ROM. `start()` (`../src/init.c`) is the whole game — all 75 functions, unchanged — and this
directory supplies only the hardware boundary the harness models away.

It lives at `recreate/atari/` rather than `recreate/render/atari/` (BuggyBoy's path) because Joust
has no host `render/` layer for it to sit under: there is no PNG renderer here, only the harness.

## Status

| milestone | what it proves | state |
|-----------|----------------|-------|
| **M1** title screen | the on-target framebuffer IS the title picture the staged program image carries, byte for byte, with the title text over it — and over *exactly* the four pinned scanline bands, nowhere else | ✅ `smoke.py title` |
| **M2** gameplay | `'1'` really drove the ONE-player arm (`two_player_mode == 0`, `players_alive == 1`, read out of the image); 240 frames render a real scene (platforms, ground, riders, the score bar) and it MOVES between two dumped frames; a `play_sound` command list reaches XBIOS `Dosound` during the frame loop | ✅ `smoke.py frames` |
| **M3** quit / restart | Ctrl-C runs the verified `quit_to_desktop`, hands the machine back and ends the process — from play *and* from the title screen; R restarts the game | ✅ `smoke.py quit` / `quittitle` / `restart` |
| **M3** `HIGH.SCO` | a modified record goes in, the game reads it, the quit path writes it back out through real GEMDOS, and a reboot shows it on the title screen's HIGH SCORE line **and only there** | ✅ `smoke.py hiscore` |
| **M3** side-by-side | our on-target title framebuffer is **byte-identical** to the shipped binary's, found at the original's own Physbase in a dump of its RAM | ✅ `smoke.py original` |
| **M4** frame differential | the same equality carried through starting a game and **240 frames of play**: both binaries anchored on one Hatari, framebuffers byte-compared at frames 1, 115, 150, 180, 210 and 240 — **identical at every one**, and each of those depths is one where the screen is MOVING (the neighbouring frame differs by 25-287 bytes), so each detects a one-frame mis-anchor | ✅ `smoke.py framediff` |
| **M3** joystick | the IKBD path is live — ~1000 replies filed per run, and every wait loop in the game ends on one. Steering is a GUI check: headless Hatari has no stick to press (§11) | partial, by construction |

Verified on **EmuTOS** (Hatari's bundled `tos.img`) and **TOS 1.04**, which produce byte-identical
framebuffers and identical `STATS.BIN` counters. **TOS 1.02 never runs the program at all** under a
Hatari GEMDOS drive (not one beacon appears) — a Hatari/TOS hard-disk limitation, not a property of
this build.

Every smoke **runs Hatari to the end of `--run-vbls` and asserts a clean exit** rather than killing
the emulator once the dump lands. That is not tidiness: the program `Pterm`s long before the
emulator stops, so everything after it is TOS running on its own with whatever the shim left hooked,
and an incomplete hand-back is only visible *there* (see "The bugs found on target"). The
assertion is Hatari's own exit status plus its log, filtered for faults whose PC is outside the TOS
ROM.

## Use

```bash
brew install m68k-elf-gcc hatari        # one-time

bash atari/build.sh title     && python3 atari/smoke.py title      # M1: byte-check the title screen
bash atari/build.sh smoke     && python3 atari/smoke.py frames     # M2: 240 frames, sound, exit
bash atari/build.sh quit      && python3 atari/smoke.py quit       # M3: Ctrl-C during play
bash atari/build.sh quittitle && python3 atari/smoke.py quittitle  #     ...on the title screen
bash atari/build.sh restart   && python3 atari/smoke.py restart    #     R restarts, then Ctrl-C
bash atari/build.sh title && bash atari/build.sh quit
python3 atari/smoke.py hiscore                                     # M3: HIGH.SCO round trip
python3 atari/smoke.py title && python3 atari/smoke.py original     # M3: vs the shipped binary
bash atari/build.sh framediff && python3 atari/smoke.py framediff   # M4: vs it frame by frame

bash atari/build.sh        && bash atari/run.sh                    # play it in the Hatari GUI
bash atari/run.sh original                                         # the shipped binary, same setup
```

In the GUI build, `'1'`/`'2'` (or fire) start a game, **Ctrl-C** quits to the desktop and **R**
restarts. `--joy1 keys` makes the cursor keys and right-Ctrl joystick 1.

`build.sh smoke [N]` takes a frame count; the default is 240, chosen to be past frame 156 — the
first frame on which the game itself asks for a sound. `smoke.py` finds a TOS ROM in
`$JOUST_TOS_ROM`, then Hatari's bundled one, then `tools/hatari/TOS*.img`; **run it against both**,
which is how the first of the two on-target bugs below was found. Hatari needs `--memsize 4` because the 1 MiB game image is the program's
BSS. `build/` and `disk/` are gitignored build artifacts.

## Pieces

| file | role |
|------|------|
| `joust_main.c` | the shim: build the image, wire screen/palette/IKBD, call `start()` |
| `joust_os.s` | `_start`, the TOS trap wrappers, the IKBD joystick-packet handler, and `setjmp`/`longjmp` (no libc here) |
| `shim_include/os.h` | the real-TOS shadow of the kit's modelled `os.h` — **the seam** (below) |
| `shim_include/tos.h` | the trap wrappers' prototypes |
| `shim_include/string.h` | a freestanding `<string.h>` (this bare-metal GCC ships no libc) |
| `gen_image.py` | dump the **pre-relocated** program `[0x10000, 0x2b7ae)` to `JOUST.IMG`, via the kit's own loader |
| `tos.ld` / `mkprg.py` | link at base 0, then wrap the ELF into a GEMDOS `.PRG` with a relocation table (copied verbatim from the BuggyBoy build) |
| `build.sh` | compile + link + wrap + stage `disk/`; one mode per on-target check (`title`, `smoke`, `quit`, `quittitle`, `restart`), each also kept as `build/JOUST-<mode>.PRG` |
| `smoke.py` | headless Hatari: boot, run to completion, read `SCREEN.BIN` / `SCREEN0.BIN` / `STATS.BIN` / `HIGH.SCO` back, check them. Also `hiscore` (three chained boots) and `original` (RAM-dump comparison with the shipped binary) |
| `run.sh` | interactive Hatari, ours or the original |

## The boundary decisions

### 1. The seam is the include path, not the linker

The cores call the kit's `os_*` helpers, and those are `static inline` in
`tools/recreate_kit/include/os.h` — there is no symbol to override. So `build.sh` puts
`shim_include/` **ahead of** the kit on the include path; `shim_include/os.h` renames the five
modelled helpers whose answer is real hardware out of the way, pulls the kit's header in with
`#include_next` for everything else, and defines the real ones:

| helper | on target |
|--------|-----------|
| `os_bconstat` / `os_bconin` | real BIOS traps — a real keyboard |
| `os_giaccess` | real XBIOS Giaccess — the real YM2149 |
| `os_random` | real XBIOS Random, so `init_game`'s RNG seed is not a constant |
| `os_super` | a **no-op** returning the model's token; the shim owns the privilege switch |
| `os_fopen` / `os_fread` / `os_fwrite` / `os_fclose` | **the kit's model, kept** (below) |

Two kit sources are left out of the link instead: `src/dosound_log.c` (the shim's `g_dosound` issues
the real trap) and `src/os_refusal.c` (`-DOS_NO_REFUSAL_TALLY`, the switch the kit's `os.h` header
already anticipates for exactly this build). **Nothing in the kit or in `../src/` was changed**, and
the differential `.so` never sees this directory, so `make test` is untouched.

### 2. Files stay on the model; the shim does the real I/O at the edges

`init_system` opens `HIGH.SCO` from inside the init chain, which the original runs in supervisor
mode — and GEMDOS handle allocation misbehaves from supervisor under Hatari's GEMDOS drive (the
BuggyBoy build shipped that bug). Keeping the kit's staged-file model means the cores' file calls
are pure image operations with no privilege requirement at all: the shim `Fread`s `HIGH.SCO` into
the staging area (`OS_FS_STAGING`) and fills in one table entry before the game starts, exactly as
`harness.stage_files` does. Same bytes, no trap in the middle.

The write-back is the mirror: `save_hiscore` puts the 26-byte record into that staging area through
`os_fwrite`, and the shim copies it out to the real `HIGH.SCO` on the quit path, at the length the
model's own table entry reports and behind the same `hiscore_dirty` gate the routine uses. That gate
is always set, and that is the ORIGINAL's behaviour rather than an accident — `init_system` marks a
successfully loaded file dirty, so every Ctrl-C rewrites it (`../src/init.c` calls it out as
reproduced, not fixed).

### 3. Privilege: user mode, with balanced `Super` pairs

The original stays in supervisor for its whole run. This build stays in **user** mode and takes
supervisor only in balanced `Super(0)`/`Super(ssp)` pairs around the three privileged pokes (the
KBDVBASE vectors, the `conterm` byte, the VBL queue). The cores reach hardware only through traps,
so nothing is lost, and GEMDOS stays usable throughout.

### 4. The screen: point TOS at the in-image framebuffer (no copy-flip)

`screen_base` is `OS_SCREEN_BASE` (0x8000) — the kit's modelled `Physbase` answer, which
`init_system` stores and every draw routine addresses from. Rather than copy 32000 bytes to the real
`Physbase()` each frame (BuggyBoy's approach, ~20 ms of an 8 MHz frame), the shim points TOS at the
image: `Setscreen(image + 0x8000, image + 0x8000, -1)`. `tos.ld` aligns `.bss` to 256, which is all
the shifter requires. This is also the *more* faithful choice — Joust has no double buffer and draws
straight into the displayed screen, so on-target tearing is the original's tearing.

`Setscreen`, not a poke at `$ffff8201/8203`: TOS's own VBL reloads the shifter from `_v_bas_ad`, and
only `Setscreen` updates that.

### 5. The palette: pushed by the shim, through `_colorptr`

`xbios_setpalette` (`../src/init.c`) returns the table address and both of its callers **drop it**,
and `init_video`'s `Setpalette` is not even a call — because the trap writes the shifter, not
memory, so the kit models it as a pure no-op and the differential could only ever verify the
argument the *original* pushed. Nothing in the reconstruction can put a colour on screen.

So a 50 Hz VBL handler does it: one longword into TOS's `_colorptr` (0x45a), which TOS's own VBL
loads into the 16 pens and clears — precisely what `Setpalette` does. It points at
`image + title_palette` while the title screen is up (which is also what *animates* it:
`cycle_palette` and the six-pen ring rewrite that table in the image every attract pass) and at
`image + game_palette` afterwards.

The switch between the two is exact rather than a guess. `shim_psg_written()` fires on the **first
Giaccess WRITE** of the run, and the only routine that writes the YM2149 through Giaccess is
`snd_tone_sweep`, whose only caller is the tail of `init_video` — the call immediately after
`title_screen` returns. (`play_sound` reaches the chip through `Dosound`; `snd_poll_done` only
*reads* register 7.)

### 6. The IKBD interrogate, which the reconstruction cannot issue

`request_ikbd_packet` (`../src/input.c`) clears `ikbd_packet` and **issues no `Ikbdws`** — the trap
has no image effect, so the differential could not hold it, and both `../STATUS.md` and
`../include/input.h` say in as many words that an on-target build owes it. Without it every wait
loop in the game spins for ever. Three additions close it:

- the shim sends the game's own `$15` byte (`ikbd_cmd_joymode`, interrogation mode) and one `$16`
  (`ikbd_cmd_joyread`) at startup — both read out of the image, not invented;
- `joy_handler` (`joust_os.s`) **chains** another `$16` straight at the ACIA as it files each reply,
  so one interrogate is permanently in flight and a wait costs about the 2.6 ms of one 2-byte reply
  at 7812.5 baud — which is what the original pays;
- the VBL handler re-primes if the reply slot has stayed empty for two vblanks, covering a chain
  broken by a reply that arrived with the ACIA transmitter busy.

`joy_handler` cannot BE the original's handler at `0x102da` (`move.l a0,ikbd_packet`): that stores a
real address, and the cores read `ikbd_packet` as an **image offset** (`image[packet + 0]`). So it
copies the two bytes into a fixed image slot (`JOY_PACKET_BUF`, 0x700) and publishes that offset.

Two things about it are worth recording.

`joy_handler` and the VBL watchdog can both write the ACIA, and nothing locks them against each
other: a watchdog `$16` issued in the vblank between a reply landing and the handler's own chained
`$16` costs one interrogate (the ACIA transmitter is busy, so the handler's `btst` fails and it
skips). The next reply re-chains, so the failure mode is one dropped interrogate, not a stall — and
the watchdog's own two-vblank timer is what recovers it either way.

And `hiscore_joystick_input` is reconstructed from *past* its wait and so asks for no packet of its
own — `../include/input.h` warns that the entry screen would act on a stale reply for ever. The
chain keeps the slot fresh, so on target it does not.

### 7. Everything installed is saved, and handed back before the process ends

Four things point TOS at code and state inside this process: the KBDVBASE joystick and mouse
vectors, the `_vblqueue` pointer with `nvbls`, and the `conterm` byte. `shim_teardown()` is the
mirror of all four and runs before any `Pterm`.

This is not hygiene, it is the fix for a measured halt. The joystick vector is the sharp one: the
IKBD is still in interrogation mode when the program ends, `joy_handler` chains the next `$16` off
every reply, and after `Pterm` it is doing that from memory GEMDOS has handed back. On TOS 1.04 that
is `Address Error reading at address $e69, PC=$12800` and then
`Detected double bus/address error => CPU halted!`, about a second after the program exits — which
is precisely why the smokes now run the emulator on past the dump instead of killing it.

The IKBD itself is put back with the **game's own** two command strings, the ones the original's
quit tail sends: the reset `$80 $01` (`ikbd_cmd_reset`) and the mouse-reporting byte `$14`
(`ikbd_cmd_mouse_rel`). `../src/input.c`'s `restore_system` is the image half of that hand-back; the
traps are the half no reconstruction has.

`shim_teardown` runs on **every** exit path there is — the game's own Ctrl-C quit (§10) and the
SMOKE builds' frame-limit dump alike. Alongside the four undos it makes the FIVE off-image trap
calls the reconstruction's quit tail has no reconstruction for: `restore_system` (`../src/input.c`)
puts back the three bytes it can see, all of them inside the image, and its `Setscreen`, two
`Ikbdws`, `Super` and `Setpalette` touch nothing the differential could hold. Two of those five
cannot use the image's answer — `Setscreen` is handed **TOS's own** log/phys base, saved before the
shifter was pointed at the in-image framebuffer (the original never moved the screen, so it passes
-1/-1), and `Setpalette` is handed the palette **the shim** read back at startup, because the one
`save_palette` stored is sixteen zeros: the kit models XBIOS `Setcolor` as answering 0, so restoring
the image's copy would hand the desktop a black screen.

### 8. The `D0`/`D2` hand-off — accepted as-is

`update_objects` reads `D0` and `D2` before writing them, and in the original they hold whatever
`read_joysticks`' last `control_player` left behind. A C `start()` cannot carry a register across a
call, so it passes **zero** — the one fidelity gap in the reconstruction, disclosed on `_start`'s
row in `../STATUS.md`.

This build keeps the zeros and does not paper over them. The offline evidence is that it does not
matter on any reachable frame: `D0` only reaches `rng_advance`'s restart offset when the cursor
wraps and `D2` only the type-1/2 probe, and a **sixty-frame** sweep moving either register alone and
both together produced the identical image **below the stack guard** every frame (`../STATUS.md`,
limit 1). The qualifier is load-bearing and is quoted rather than dropped: an earlier revision of
that row claimed the opposite on a *whole-image* compare, and the two bytes that appeared to move
were the oracle's own saved registers, above the guard and outside the comparison. Closing it
properly means `read_joysticks` handing its callee's `D0`/`D2` back, i.e. a contract change to two
verified functions; that is an integrator's decision, not the shim's, and it is recorded here rather
than taken.

### 9. The headless keystroke

A headless run has no keyboard, so the SMOKE builds offer a SEQUENCE of keys at the shim's
**console seam** — the same place TOS delivers a real one. `build.sh` sets it: the keys, and how
many console polls to wait for each after the previous was taken. That wait is a natural clock in
both phases, because the title screen polls ~400 times per attract pass while during play
`poll_quit_key` is exactly one poll per frame — so `quit` is "type '1', play 60 frames, press
Ctrl-C" and `restart` adds "R, then Ctrl-C from the new title screen".

Two conditions gate each key: the poll count above, and the real `Bconstat` having nothing waiting
on the poll that serves it — so an interactive key always wins. (The first is a poll *count*, not a
silence detector; a real key arriving early is taken by the second condition, not the first.)

Everything downstream of that byte is the verified reconstruction, and `STATS.BIN` is what says so:
`two_player_mode == 0` and `players_alive == 1`, read out of the image at the dump, are
`start_game`'s one-player arm and nothing else. That check exists because the choice is **not
legible in a framebuffer** — asserting on pixels would have left the `'1'` path assumed. What the
headless run does *not* prove is TOS's own keyboard driver; `run.sh` is where a human proves that.

### 10. Quit and restart, which `start()` cannot take itself

Three of the reconstruction's exits are result codes `start()` drops — `INPUT_QUIT`,
`INPUT_RESTART`, `CHECK_HIGHSCORE_RESTART` — and dropping them is CORRECT, because the original's
twenty-one `jsr`s drop them too: there the routine that took such a path never came back. In C it
does, so without the shim the on-target game cannot be quit or restarted at all. The shim finishes
them from the only place it gets control, the OS seams the cores call, since `start()` never returns.

**Ctrl-C is WATCHED, not intercepted**, because `quit_to_desktop` is verified code that has to run —
it silences the chip, writes the record into the staged file and puts the image's system state back.
So: the console seam sees the key go to the game; `quit_to_desktop`'s own first act, the `Dosound`
silence, confirms the tail is running; and the next seam of any kind — the tail having returned —
takes the exit.

Two invariants hold that scheme up, and both are load-bearing enough to be worth stating where a
future editor will trip over them (they are also on the hook list in `shim_include/os.h`):
**the file helpers must never gain the exit hook** — `quit_to_desktop` calls all three of them
through `save_hiscore` while the shim is already in `QUIT_TAIL_RUNNING`, so a hook there would fire
the exit mid-record and truncate or lose the write-back; and **no other `Dosound` can occur between
the key and the tail's own** — both readers that act on Ctrl-C test the key and call
`quit_to_desktop` in the same statement, and `check_highscore`'s entry loop, the one reader that
ignores the key, issues none at all, which is what makes "a second console poll instead" a safe way
to recognise it. That is one seam later than the original's `Pterm`, and the cost differs by path. From play it is
one more frame. **From the title screen it is the whole of `init_video`**: `title_screen` returns
`TITLE_QUIT`, `start_init_chain` drops it and calls `init_video` next, whose first hooked seam is
`snd_tone_sweep`'s `Giaccess` at the very *end* — so the title picture is blanked by `fill_screen`
and the playfield, score bar and lives are painted before the exit lands (measured: `psg_writes = 0`
in the `quittitle` run, i.e. it stops on that sweep's very first register write). On screen that is
one frame of game before the desktop returns, and it is why `quittitle`'s dumped framebuffer is a
game screen rather than a title one. Neither divergence outlives the exit — the shim puts TOS's own
screen and palette back — but the title one is a visible flash, not 20 ms of nothing.

**If the game does NOT react, the shim quits on its behalf.** A Ctrl-C that reaches a second console
poll without that `Dosound` is one the game ignored — which `check_highscore`'s name-entry loop does,
since `hiscore_key_input` has no Ctrl-C case and that loop never returns to `poll_quit_key`. Without
this the game would be unquittable there. The shim then calls `quit_to_desktop(image)` itself: the
exported routine, not a copy of it.

**R restarts** by `longjmp`ing back to a `setjmp` in `joust_main` and re-entering `start()`. The
original jumps to `RESTART_ENTRY` = `_start+6`, i.e. back to `init_game` with `init_system` SKIPPED;
re-entering `start()` runs `init_system` as well. Running the VERIFIED `start()` is worth that,
because the alternative is a second copy of `_start`'s twenty-one calls living in the shim — but the
two things `init_system` writes that would be **observable** are snapshotted and put back at
`shim_init_game_started()`, which is `init_game`'s own `Random` trap and so exactly where the
original resumes: `two_player_mode` (zeroed, which would lose the mode a fire-button start reuses)
and the in-memory high-score record (which `load_hiscore` would overwrite from the staged file,
discarding a score just typed). "Two" is not a claim that `init_system` writes nothing else — it
re-saves `saved_rez`, the 16-word `saved_palette`, `conterm_save`, the two in-image KBDVBASE vectors
and the boot scratch too, and every one of those is image-only state that only the reconstruction's
own quit tail reads, while the real machine is handed back from the shim's copies.

**The shim's own view of the run is reset with it**, and forgetting that was a bug: `title_over`
latches on the first `Giaccess` write and never clears, so the restarted attract screen ran under the
GAME palette (measured: zero title-palette loads after a restart) and a `SMOKE_FRAMES` build would
have counted title polls as frames and terminated on the title screen.

**R is only a restart during play** — `title_over` set and `game_over_flag` clear — and that is a
deliberately narrow trade with an edge on each side, *neither of which the original has*:

- `game_over_flag` **set**: the name-entry screen may be up, and there R is a **letter** being typed
  into the name. But the original's `poll_quit_key` tests nothing at all, so between `draw_messages`
  setting the flag mid-loop and `init_game` clearing it there is a window in which the original
  restarts and this build does not.
- `title_over` **clear**: the attract screen. `game_over_flag` is clear there (`init_game` runs just
  before `title_screen`), so that gate alone is wide open — and the original ignores R on the title
  screen like any other key, `title_screen` having no R case at all.

The shim can only see what state the game is *in*, never which reader consumed a key, so it buys
fidelity on the two screens where R should do nothing at the cost of one window where it should.

### 11. The frame differential: pinning the shipped binary from outside

`smoke.py framediff` runs the shipped `bin/JOUST.PRG` and this build on the same Hatari, ROM and
`HIGH.SCO`, and byte-compares their framebuffers at matched frame counts. Our side is scripted
through the shim; the shipped side has no seams at all, so everything is done to it from Hatari's
debugger, at run-time addresses derived from the load base that run discovered:

- **The load base is found, not assumed.** A 64-byte signature from a relocation-free part of the
  `.PRG` is searched for in a full RAM dump; its address minus its file offset is the base. It is
  genuinely not a constant — **0x12596 under TOS 1.04 and 0x1b018 under EmuTOS** in the same test.
  The signature is taken from the END of that reloc-free run: the start of it is the dead floppy
  loader's variable block, six bytes and fifty-eight zeros, distinctive only by luck.
- **The `'1'` is injected at the Bconin trap, not after it.** Forcing `Bconstat` to answer "a key is
  waiting" makes the game call `Bconin` — which **blocks**, because TOS's buffer is empty, and the
  run stops there for ever (measured). So the breakpoint sits *on* the trap and sets `D0` and `PC`
  past it. It lands on the first console poll of the first attract pass, exactly where our scripted
  key lands, and the byte itself is read out of `joust_main.c` so there is no second spelling of it.
- **The frame anchor is `poll_quit_key`'s entry**, which the frame loop enters once per frame and
  which exactly one `jsr` in the whole image refers to. Hatari's `:<count>` breaks on every count-th
  hit and `:once` retires it, so one breakpoint per sample frame reads off that sample exactly. (A
  count of `1` is rejected; frame 1 is a plain `:once`.) An action file that ends in `cont` still
  leaves the debugger at its prompt, so the run is fed a supply of `c` on stdin or the emulation
  stops dead after the first breakpoint.
- **On our side the frame number is a console-poll count.** `frames` counts `os_bconstat` calls once
  the title is over, which coincides with `poll_quit_key` entries only because the two other console
  readers are unreachable at this depth: `pause_until_key`'s spin needs a P keypress and
  `hiscore_key_input` needs a game over. Measured for the 121-frame run: `console_polls = 122`,
  i.e. one title-screen poll plus 121 frames. If either reader ever became reachable in a sampled
  window the two sides would be counting different things.

**Result: identical at frames 1, 115, 150, 180, 210 and 240, on EmuTOS and on TOS 1.04.** The
comparison is bitplanes, which is the right thing: the palette is off-image on both sides (§5).

**The sample depths are chosen, not spread.** With the sticks centred the screen is static from about
frame 2 to frame 110 — the rider settles and then nothing moves until the first enemy is on the
board — so evenly spaced depths would mostly have re-sampled the same painted frame. Each depth here
has a *moving* neighbour (frame N differs from N+1 by 113, 25, 227, 281, 282 and 287 bytes), which is
what makes every one of them able to detect a mis-anchor.

Three guards and two controls, because a compare that cannot fail proves nothing:

- **Length.** `zip` stops at the shorter side, so a truncated — or empty — dump compares equal as far
  as it goes and would report IDENTICAL (demonstrated: a zero-byte shipped dump passed). Every
  framebuffer is now required to be exactly 32000 bytes on both sides, and our side additionally
  reports the total bytes its dumps wrote (`frame_bytes_written`) so a `savebin` or `Fwrite` that
  silently did nothing is caught rather than read back as a match.
- **Determinism.** The shipped side is run a second time with the identical script and must produce
  identical dumps — it is the side carrying all the machinery, so it is the side whose repeatability
  is worth asserting.
- **Sensitivity — a real injected fault.** The shipped side is re-run **anchored one frame late** and
  the comparison must FAIL. It does, at all six samples (25-287 bytes each, with the first differing
  byte and row named). An earlier version of this control compared `ours[early]` against
  `shipped[late]` and called that sensitivity; that is a *theorem* once the main compare has passed,
  and it stayed green in a run where the main compare correctly failed. The lesson is in
  `docs/on-target-execution.md`: control the control with a fault you inject, not with a rearrangement
  of numbers you already hold.

**The RNG pin is precaution, and measurably inert here.** Joust has no arithmetic generator: `rng_ptr`
walks the program's own text and callers read the word under it (`../src/rng.c`). Those bytes are
*not* the same on both sides — 1117 relocation sites fall in that window, and a relocated longword
holds *file value + load base* — so forcing the same XBIOS `Random` answer would pin only the starting
offset into two different streams. Both sides therefore park the cursor in the largest
relocation-free stretch (Ghidra `0x1551a`), and the mode checks our cursor stayed inside it (the
bound is computed from the `.PRG`'s own relocation table, not written down; measured travel 2904
bytes of 6896).

But parking it changes nothing that reaches the screen at these depths. Parking **both sides at
`0x10000` instead — a relocation-*bearing* region where the two loads genuinely hold different
bytes — still leaves all six frames identical.** The stream is consulted (the cursor moves) and
nothing it feeds is drawn yet. Worth knowing too: the parked stretch is 203 bytes of code followed by
a 6,648-byte run of zeros, so the pinned regime is constant-zero randomness — artificial, not a
neutral sample of the game's own entropy. The pin is kept because it costs nothing and makes the
comparison honest at depths where the RNG *does* reach the screen; it is not the reason these frames
match.

**And the `D0`/`D2` gap did not separate.** §8's fidelity gap — our `start()` passes zeros where the
original carries `read_joysticks`' leftovers — is exactly what this test would expose first, and the
offline evidence for it was a sixty-frame sweep below the stack guard. Here it is two hundred and
forty frames on a real 68000 against the real binary, and every sampled frame is equal. That does not
*prove* the registers are dead — no neutral-stick run can, and the moving content is one spawning
sprite rather than a busy playfield — but it is a considerably stronger statement of the same limit,
and it is on-target evidence rather than harness evidence.

### 12. The joystick, as far as a headless run can go

The IKBD path is proven **live**: `joy_handler` files a reply and chains the next interrogate, and
`STATS.BIN` counts them — ~1000 per run, and every wait loop in the game (`read_joysticks`,
`title_screen`'s attract pass, the name entry) blocks until one lands, so the run reaching its last
frame at all is that path working. What a headless Hatari cannot do is *press* a stick: `--joy1 keys`
maps host keys and there is no host keyboard, so `player_x`/`player_y` in `STATS.BIN` show the rider
under gravity alone. Steering is therefore a GUI check — `run.sh`, cursor keys and right-Ctrl.

That leaves the `D0`/`D2` decision of §8 where it was — and §11 is now the strongest evidence for
it: 120 frames against the shipped binary, byte-identical. A *steered* differential would be
stronger still, and needs a deterministic way to press a stick on both sides; Hatari's debugger can
force our side's IKBD packet but the shipped side reads TOS's own buffer, so that is future work
rather than something this mode quietly skips.

## Known gaps

- **The high-score name entry does not END.** `check_highscore`'s entry loop is left, in the
  original, by either reader jumping to `RESTART_ENTRY`; the C returns `CHECK_HIGHSCORE_RESTART` and
  `start()` drops it, so RETURN or fire types the name and the screen stays up. §10's trick does not
  reach it: unlike Ctrl-C there is no trap the shim can watch to tell "the reader ended the entry"
  from "the reader accepted a letter", and deciding it in the shim would mean a second copy of
  `hiscore_finish`'s gate. **Ctrl-C works there** (§10's second branch), so the screen is an
  inconvenience rather than a trap. Closing it properly wants a seam in the core.
- **`control_player`'s restart is not wired either.** Both riders dead on an empty slot sets
  `game_over_flag` and, in the original, jumps to `RESTART_ENTRY`; the C returns `CONTROL_RESTART`
  through `read_joysticks` and `start()` drops that too. The game keeps playing instead of
  restarting. Same shape as the entry loop and the same reason.
- **A NEW record has not been round-tripped, only a changed one.** `smoke.py hiscore` proves the
  path end to end — a modified `HIGH.SCO` goes in, the game reads it, `save_hiscore` writes it back
  into the staged file, the shim copies it out through GEMDOS, and a reboot shows it on the title
  screen's HIGH SCORE line and only there. What no headless run has produced yet is a record the
  PLAYER typed, because that needs a game over (four lives lost with the sticks centred) and then
  the name entry above, which cannot be ended. Deferred on purpose rather than faked.
- **1 MiB machine.** The image is a 1 MiB BSS array, so the PRG needs `--memsize 4`. The original
  runs on a 520 ST. Shrinking the image to the ~0x2c000 the program actually occupies plus the
  screen and the file staging is possible but needs `OS_IMAGE_SIZE`, `OS_FS_*` and the kit's memory
  map to move together — future work, deliberately not attempted here.
- **The monochrome branch is dead code on target too.** `init_system` reads `Getrez` as the model's
  constant 0, so a mono machine gets the colour game rather than `MONO.ERR`.
- **Joystick steering is only checked in the GUI** — see §11 for what the headless run does prove.

## Reviewed and deferred

The pre-commit review found four things worth doing that are **not** in this change, because each
is a change to a verified core or to the shared kit rather than to the shim. They are recorded here
rather than half-taken:

- **An `os_pterm()` seam is the right depth for §10.** The original *traps GEMDOS Pterm* at exactly
  the two sites that consume Ctrl-C, and the reconstruction dropped the trap because it has no image
  effect. A seam there — no-op in the harness, `shim_quit()` on target — would delete the whole
  watch-then-confirm state machine, both invariants above, the second-console-poll fallback **and**
  the one-seam divergence. It is `docs/on-target-execution.md`'s own §5 recipe applied to this exit.
- **Splitting `start()` would delete the restart snapshot.** `start()` is `start_init_chain(); for(;;)`
  and `RESTART_ENTRY` is literally "everything but the first call". Exposing
  `start_at_restart_entry()` is a few lines in `../src/init.c`, is differentially testable exactly as
  the two existing rotations are, and removes the snapshot, the replay and the `os_random` hook —
  along with their dependence on `init_game` being the only caller of `Random`.
- **Two kit candidates.** The headless-Hatari launcher now exists three times (here and twice in
  BuggyBoy's `render/atari/`) and the copies have already diverged in a way that matters — only this
  one asserts on the exit status. The 68000 trap wrappers are a second such library, and the
  `movem.l %d2/%a2` save every one of them needs is a bug class the oracle cannot see. Both belong
  next to `tos_probe.py` in `tools/recreate_kit/`; moving them is a kit change.
- **The key script could be staged, not compiled in.** Five `-D` flag sets, five link cycles and six
  cached `build/JOUST-<mode>.PRG` exist only to vary three ASCII bytes. Reading them from a staged
  file would leave one SMOKE build and put the scenario data in `smoke.py` beside the assertions
  about it. Until then each check boots the build made for it and refuses one older than the sources,
  so a mismatch is named rather than surfacing as a behavioural red.

Two smaller ones declined outright: a `.macro` for the five no-arg XBIOS wrappers (it would rewrite
proven trap glue for line count), and having `hiscore`'s first phase reuse `out/screen_title.bin`
instead of booting (a self-contained baseline is worth the 6 s).

## The bugs found on target

All three are the shape `docs/on-target-execution.md` warns about — real behaviour, in code the
differential harness cannot execute at all — and none was visible under the setup that found the
previous green.

**1. A GCC addressing mode the 68000 reads differently (taxonomy class 6).** The VBL palette pusher
first wrote `$ffff8240..$ffff825e` directly, as a 16-iteration loop over a `volatile uint16_t *`.
GCC compiled it to

```
move.w (%a0)+,(%a0,%d0.l)
```

— and on the 68000 the destination effective address is computed **after** the source
postincrement, so every pen landed one register high and the sixteenth write went to `$ffff8260`,
the **resolution** register, carrying pen 15's `0x0777`. TOS 1.04 hung on the spot; EmuTOS survived
it, so the bug was invisible on the default ROM and only appeared when a second one was tried. Fixed
by the `_colorptr` route in §5 — one longword store, no shifter access, no addressing mode to get
wrong. *Lesson: run the smokes on more than one TOS ROM.*

**2. Vectors installed and never handed back.** The KBDVBASE joystick and mouse vectors were
installed and the `_vblqueue` swapped, and the exit path unhooked only the VBL queue before `Pterm`.
The IKBD was left in interrogation mode with `joy_handler` chaining `$16` off every reply — from
memory GEMDOS had taken back. Measured on TOS 1.04, run to completion:
`Address Error reading at address $e69, PC=$12800`, then
`Detected double bus/address error => CPU halted!`, exit status 1. Fixed by §7's `shim_teardown()`;
the same run now exits 0 with no fault outside the TOS ROM.

*Lesson, and it is the sharpest of the three: the smokes of the day passed this build, because they
killed Hatari a third of a second after `SCREEN.BIN` appeared.* A harness that stops watching at the
moment of success cannot see a shutdown at all. Running to the end of `--run-vbls` and asserting on
the exit costs eleven seconds a run and is now part of every check.

**3. A hand-written `setjmp` that trusted the stack.** §10's restart needs an unwind, and a
freestanding m68k build has no libc to get one from, so `shim_setjmp`/`shim_longjmp` are ten
instructions in `joust_os.s`. The first version saved `%sp` as it stood *inside* setjmp — pointing at
its own return address — and let `longjmp`'s `rts` pick the address up from there. That slot is dead
the moment setjmp returns, and every call the game makes afterwards reuses it. Measured: the longjmp
fired and the instruction after `setjmp` never ran. The buffer now holds the return address itself.
A second, quieter half of the same bug: without `__attribute__((returns_twice))` GCC compiles the
call as one that returns exactly once and reasons the landing away — also measured, and also silent.

*Lesson: two of these three were only found because a SECOND observation was added — a second TOS
ROM, and letting the emulator run past the exit. On target, the cheap extra observation is the tool.*
