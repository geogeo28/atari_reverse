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
| **M3** | joystick play, `HIGH.SCO` round-trip, the quit path, side-by-side vs the original | not started — see "What M3 needs" |

Verified on **EmuTOS** (Hatari's bundled `tos.img`) and **TOS 1.04**, which produce byte-identical
framebuffers and identical `STATS.BIN` counters. **TOS 1.02 never runs the program at all** under a
Hatari GEMDOS drive (not one beacon appears) — a Hatari/TOS hard-disk limitation, not a property of
this build.

Both smokes **run Hatari to the end of `--run-vbls` and assert a clean exit** rather than killing
the emulator once the dump lands. That is not tidiness: the program `Pterm`s long before the
emulator stops, so everything after it is TOS running on its own with whatever the shim left hooked,
and an incomplete hand-back is only visible *there* (see "The bugs found on target"). The
assertion is Hatari's own exit status plus its log, filtered for faults whose PC is outside the TOS
ROM.

## Use

```bash
brew install m68k-elf-gcc hatari        # one-time

bash atari/build.sh title  && python3 atari/smoke.py title    # M1: byte-check the title screen
bash atari/build.sh smoke  && python3 atari/smoke.py frames   # M2: 240 frames, sound, clean exit
bash atari/build.sh        && bash    atari/run.sh            # play it in the Hatari GUI
bash atari/run.sh original                                    # the shipped binary, same setup
```

`build.sh smoke [N]` takes a frame count; the default is 240, chosen to be past frame 156 — the
first frame on which the game itself asks for a sound. `smoke.py` finds a TOS ROM in
`$JOUST_TOS_ROM`, then Hatari's bundled one, then `tools/hatari/TOS*.img`; **run it against both**,
which is how the first of the two on-target bugs below was found. Hatari needs `--memsize 4` because the 1 MiB game image is the program's
BSS. `build/` and `disk/` are gitignored build artifacts.

## Pieces

| file | role |
|------|------|
| `joust_main.c` | the shim: build the image, wire screen/palette/IKBD, call `start()` |
| `joust_os.s` | `_start`, the TOS trap wrappers, and the IKBD joystick-packet handler |
| `shim_include/os.h` | the real-TOS shadow of the kit's modelled `os.h` — **the seam** (below) |
| `shim_include/tos.h` | the trap wrappers' prototypes |
| `shim_include/string.h` | a freestanding `<string.h>` (this bare-metal GCC ships no libc) |
| `gen_image.py` | dump the **pre-relocated** program `[0x10000, 0x2b7ae)` to `JOUST.IMG`, via the kit's own loader |
| `tos.ld` / `mkprg.py` | link at base 0, then wrap the ELF into a GEMDOS `.PRG` with a relocation table (copied verbatim from the BuggyBoy build) |
| `build.sh` | compile + link + wrap + stage `disk/` |
| `smoke.py` | headless Hatari: boot, run to completion, read `C:\SCREEN.BIN` / `SCREEN0.BIN` / `STATS.BIN` back, check them |
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
`harness.stage_files` does. Same bytes, no trap in the middle. The write-back is M3's.

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

`shim_teardown` is compiled into the SMOKE builds only, because they are the only builds with an
exit at all — `start()` never returns, and the Ctrl-C path that will need it in the playable build
is M3's.

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

`smoke.py frames` has no keyboard, so the `smoke` build offers `'1'` at the shim's **console seam** —
the same place TOS delivers a real key. Two conditions gate it: the run must have made
`SMOKE_KEY_AFTER` (8) console polls, and the real `Bconstat` must have nothing waiting on the poll
that serves it, so an interactive key always wins. (The first is a poll *count*, not a silence
detector; a real key arriving before poll 8 is taken by the second condition, not by the first.)

Everything downstream of that byte is the verified reconstruction, and `STATS.BIN` is what says so:
`two_player_mode == 0` and `players_alive == 1`, read out of the image at the dump, are
`start_game`'s one-player arm and nothing else. That check exists because the choice is **not
legible in a framebuffer** — asserting on pixels would have left the `'1'` path assumed. What the
headless run does *not* prove is TOS's own keyboard driver; `run.sh` is where a human proves that.

## Known gaps

- **Restart, quit and the high-score entry do not end.** `start()` ignores its callees' results
  exactly as the original's twenty-one `jsr`s do — correct there, because the routine that took such
  a path never returns. In C they *do* return, so on target Ctrl-C runs `quit_to_desktop` and then
  carries on playing, `R` does nothing, and a game-over that beats the record re-enters
  `check_highscore` every frame. All of this is M3.
- **`quit_to_desktop` restores the image, not the machine.** `restore_system` writes `conterm` and
  the two KBDVBASE vectors *inside the image* (the kit models low memory as image bytes), and the
  five off-image calls around it — `Setscreen`, two `Ikbdws`, `Super`, `Setpalette` — have no
  reconstruction at all. `../src/input.c` says so. The machine half already exists as §7's
  `shim_teardown()`; what M3 owes is a quit path that reaches it and a `Setscreen` back to TOS's own
  framebuffer.
- **`HIGH.SCO` is read but not written back.** `save_hiscore` writes into the image staging area; the
  shim does not yet copy it out to the real file.
- **1 MiB machine.** The image is a 1 MiB BSS array, so the PRG needs `--memsize 4`. The original
  runs on a 520 ST. Shrinking the image to the ~0x2c000 the program actually occupies plus the
  screen and the file staging is possible but needs `OS_IMAGE_SIZE`, `OS_FS_*` and the kit's memory
  map to move together — future work, deliberately not attempted here.
- **The monochrome branch is dead code on target too.** `init_system` reads `Getrez` as the model's
  constant 0, so a mono machine gets the colour game rather than `MONO.ERR`.

## The bugs found on target

Both are the shape `docs/on-target-execution.md` warns about — real behaviour, in code the
differential harness cannot execute at all — and neither was visible under the setup that found the
first green.

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

*Lesson, and it is the sharper of the two: the original smokes passed this build, because they
killed Hatari a third of a second after `SCREEN.BIN` appeared.* A harness that stops watching at the
moment of success cannot see a shutdown at all. Running to the end of `--run-vbls` and asserting on
the exit costs eleven seconds a run and is now part of both checks.
