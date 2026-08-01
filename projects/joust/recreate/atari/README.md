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
| **M4** frame differential | the same equality carried through starting a game and **240 frames of play**: both binaries anchored on one Hatari, and at frames 1, 115, 150, 180, 210 and 240 **both halves of the picture compared** — the 32000 framebuffer bytes *and* the 16 hardware palette pens, read off the shifter on each side — **identical at every one**. Each depth is one where the screen is MOVING (the neighbouring frame differs by 25-287 bytes), so each detects a one-frame mis-anchor | ✅ `smoke.py framediff`, negative control `framediff-fault` |
| **M5** displayed picture | the video base is 256-aligned at run time; every smoke mode that dumps stats asserts the alignment **and** the hardware read-back; `framediff` diffs a **35-register hardware-state vector** at every anchor and the **rendered PNG** at frame 1 (the bound is measured — see §11) | ✅ `smoke.py framediff`, controls `framediff-fault` / `framediff-skew` |
| **M6** read-backs | every write this shim makes to hardware or OS state is **read back** — 15 checks across the KBDVBASE vectors, `conterm`, the VBL queue, the `_colorptr` handoff and the IKBD — and both *which failed* and *which ran* are asserted from `STATS.BIN` | ✅ every stats-dumping mode; 4 mutations verified |
| **M6** timeline | the ordered stream of palette loads and PSG writes reduced to a per-phase **shape** and compared against the shipped binary's: load counts per phase, zero redundant loads, and our PSG stream an exact prefix of theirs | ✅ `smoke.py framediff`, control `framediff-rearm` |
| **M6** the play build | the build a person actually plays, booted headless: its boot read-backs and its hardware-state vector at the title screen. Its **exit** is not asserted and cannot be — see §16 | ✅ `smoke.py play` |
| **M3** joystick | the IKBD path is live — ~1000 replies filed per run, and every wait loop in the game ends on one. Steering is a GUI check: headless Hatari has no stick to press (§11) | partial, by construction |

Verified on **EmuTOS** (Hatari's bundled `tos.img`) and **TOS 1.04**, which produce byte-identical
framebuffers and identical `STATS.BIN` counters. **TOS 1.02 never runs the program at all** under a
Hatari GEMDOS drive (not one beacon appears) — a Hatari/TOS hard-disk limitation, not a property of
this build.

Every smoke **runs Hatari to the end of `--run-vbls` and asserts a clean exit** rather than killing
the emulator once the dump lands. That assertion has two halves, and only one of them was working.
Hatari writes **all** of its logging — and all debugger output — to **stderr**, while every parser
here read `stdout`, so `check_exit`'s **line scan** for bus errors and halts had been reading an
empty string since M1. Its **exit-status** test was live throughout, and it is what caught the
hand-back bug in §7: re-run against the old `smoke.py`, that negative control still fails, on
Hatari's status 1.

So the merge did not rescue a dead check; it added the sharper class the status cannot see — **a
bus or address error Hatari logs and survives, finishing `--run-vbls` with status 0.** Measured on a
stray write issued after teardown: the old code printed `clean exit` and passed, this one reports
`FAIL: unhealthy machine after the program exited`. The streams are merged now, and a run whose
captured output does not contain Hatari's own banner raises instead of being parsed, so the scan
cannot go quiet again — and the same merge is what makes the hardware-state vector readable at all,
since the debugger's `info` output arrives on that stream too.

A related precision, because the check that reads this stream is only as good as its allowlist:
faults are excused by the **exact PC of TOS's memory-sizing probe** (EmuTOS `PC=$e00d98`, TOS 1.04
`PC=$fc0174`), not by "the PC is in ROM". A stale vector sends the CPU into ROM code, so a range
test over ROM would excuse the very class this check is for.

Running to the end rather than killing the emulator is not tidiness either: the program `Pterm`s long before the
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
bash atari/build.sh framediff && python3 atari/smoke.py framediff   # M4/M6: frames, vector,
                                                                   #   picture and timeline
bash atari/build.sh play-smoke && python3 atari/smoke.py play      # M6: the PLAY build, booted

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
loads into the 16 pens and clears — precisely what `Setpalette` does. It points at the shim's own
copy of `image + title_palette` while the title screen is up (which is also what *animates* it:
`cycle_palette` and the six-pen ring rewrite that table in the image every attract pass) and at a
copy of `image + game_palette` afterwards.

**It re-arms `_colorptr` only when the TABLE HAS CHANGED.** What that fixes is a *latent* conflict,
not a wrong colour today: the original owns the palette hardware between its `Setpalette` calls, and
re-arming every vblank stamped all sixteen pens back over anything it had done to one. Nothing in the
reconstruction issues such a write yet — `flash_hiscore_color` computes the name-entry screen's
flashing pen and *returns* it, because XBIOS `Setcolor` has no image effect for the differential to
hold — so this removes the obstacle to implementing that flash rather than repairing a live break.

It also brings the two shifter traces to the same shape. Measured with `--trace video_color` over the
pinned `framediff` run: **ours 6 full palette loads, the shipped binary 4** (per-vblank re-arming
made ours 773 on that same run). Note that "the original issues `Setpalette` at three moments" is
true of its *call sites* only — left free-running on the attract screen the shipped binary performs
**6149** loads in 20000 vblanks, because its attract loop re-issues `Setpalette` every pass.

**It introduces one vblank of latency**, and that is invisible only as far as the harness looks: TOS
used to read the game's own table at the vblank after `Setpalette`, and now reads our copy one vblank
after the change is noticed. Every place the differential samples has a constant palette, so nothing
shows; a game that changed pens per frame would be a frame behind.

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

**Result: identical at frames 1, 115, 150, 180, 210 and 240, on EmuTOS and on TOS 1.04** — and that
is now both halves of a frame: the sixteen bitplanes *and* the sixteen hardware pens.

**The palette is compared too, because bitplanes alone cannot see colour.** A framebuffer holds
plane indices; what colour an index resolves to lives in registers neither side's image contains, so
the original version of this mode was blind to the entire palette by construction and said so. Both
sides are now read off the shifter itself at the same frame anchors — ours by the shim in a `Super`
pair, the shipped binary's by `savebin $ffff8240` — so what is compared is what the screen shows,
not what either program intended. The comparison masks to `0x0777`: the ST implements three bits per
gun, and a CPU read of a shifter register returns the unused fourth bit of each nibble as whatever
was last on the bus, so *our* read carries noise there where the debugger's read of Hatari's model
does not. That is a measurement asymmetry, not a palette difference, and everything the ST can
display is inside the mask.

**It compares the pens AT the anchors, and that is its limit.** The game's palette is one constant
across all six of them, so the mis-anchor control below cannot exercise this half at all — moving the
frame moves the bitplanes and leaves the colours where they were, which makes the palette result six
repetitions of one measurement. A shim that had every pen right at each sampled frame and wrong in
between would pass, and that is exactly the shape of a *flashing* pen. The control that does bite is
a separate build (below).

**The HARDWARE-STATE VECTOR is compared at every anchor.** Thirty-five registers compared (a
thirty-sixth, the video base, is captured and printed only), taken from both
binaries at the same frame anchors and diffed like memory, so a divergence names the register:
the 16 shifter pens and the resolution register (real `savebin` reads of I/O space), the refresh
rate and V-overscan, and the 16 YM-2149 registers. That last group comes from the debugger's
`info ym` and is **Hatari's model of the chip, not a hardware read** — the PSG's file cannot be read
through `$ffff8800` without a select write, which has side effects, so there is no honest read to
take; both sides are measured identically, which is what makes the comparison meaningful. The video
base is **reported, not compared**: the two sides legitimately draw at different addresses, and its
correctness is the per-side property §12 asserts. The compare has a **floor**: if fewer than the
expected 35 names come back it reports DEGRADED and fails, so a Hatari whose `info` wording moved
cannot quietly shrink the vector and keep printing IDENTICAL over a stump — the `check_exit`
failure mode, pre-empted. Its determinism control is control 1, which now re-runs the shipped side
and diffs its vectors as well as its memory; its sensitivity control is the `framediff-fault` build.
Result: `hw vector 1/115/150/180/210/240 IDENTICAL (35 registers)` on both ROMs.

**The picture the shifter RENDERS is compared too, once.** `screenshot` drives the emulator's own
video path, so what it captures is what the screen shows — the only artefact here that is not a
memory dump. Both sides are photographed at the same frame anchor and the PNGs byte-compared:
**identical at frame 60 — 6239 bytes on EmuTOS, and the same agreement on TOS 1.04**. One frame
rather than six, because it costs two extra boots and the fault it catches — a displaced video base
(§12) — is a *constant* displacement, visible at any frame or none.

It is **stop-then-shoot**: the anchor breakpoint's action file sets `b VBL > VBL :once` (Hatari
substitutes the expression's current value, so it reads "the next vblank") and the capture happens
at that frame boundary, where the surface holds one completed frame. Without it a capture lands
part-way down a frame and mixes two — deterministic only on a static screen.

**It asserts at frame 1 only, and that bound is measured rather than assumed.** Stop-then-shoot
fixed the mixing, but a second effect remains: Hatari does not *render* every frame under
`--fast-forward`, and `screenshot` grabs the rendered surface. Our side's captures are reproducible;
the shipped side's — whose run carries far more debugger stops — are not. Repeating the capture run
and comparing each anchor against *itself*: **anchor 1 is byte-identical on 5/5 repeats on both
ROMs**; on EmuTOS **anchors 3, 4 and 5 drift**, and on TOS 1.04 **anchors 3 and 6 drift**. A drifting
anchor comes back at **3724 / 3869 / 3890 / 3933 bytes** for the *same* anchor across runs.
`--frameskips 0` narrows the window but does not close it, and turning fast-forward off around
each capture made one run longer than the whole suite. Which anchors drift is itself ROM-dependent,
so the bound is drawn where **both** ROMs are reproducible on every repeat rather than where a given
run happened to agree. Asserting on the rest would be asserting on noise: it stays an open blocker
rather than a green that means nothing.

Two more details. The status bar is turned **off**: it is emulator chrome that varies with the ROM
and the drive LED, not part of the picture the game draws. And the anchor address comes from
`STATS.BIN` — the binary reports `poll_quit_key`'s run-time address about *itself*, because
`build/joust.elf` is overwritten by every build while the per-mode `.PRG`s persist, and a stale ELF
once supplied an anchor four bytes out and the mode went green on the wrong breakpoint. Each anchor
gets exactly **one** breakpoint, whose action file does all of that anchor's work: two breakpoints
selecting the same hit disturb each other's counters, and the captures fired at shallower frames than
the dumps beside them. `one_breakpoint_per_anchor()` asserts it — per `(pc, count)`, **not** per PC:
every sample set is deliberately six breakpoints on the same address told apart by `:<count>`, so a
per-PC rule would reject the harness's own scripts. It is guarded because that failure looks like a
flaky picture rather than like a bug.

Its control is `framediff-skew`: the same run with the screen two bytes off its 256-byte boundary.
It is the sharpest demonstration in this project of what memory comparison cannot see —
**every memory check still passes** (`frame 1 IDENTICAL`, `palette 1 IDENTICAL`) while the video-base
read-back names the fault and the rendered PNGs differ.

**And this check is what would have caught the bug that shipped in M1.** The
`move.w (a0)+,(a0,d0.l)` off-by-one in "The bugs found on target" put every pen one register high —
literally "the colours are shifted" — and it was found by a hang on one TOS version rather than by
any assertion. A per-pen comparison against the shipped binary catches that at every anchor, on
every ROM, whether or not it happens to crash.

**The sample depths are chosen, not spread.** With the sticks centred the screen is static from about
frame 2 to frame 110 — the rider settles and then nothing moves until the first enemy is on the
board — so evenly spaced depths would mostly have re-sampled the same painted frame. Each depth here
has a *moving* neighbour (frame N differs from N+1 by 113, 25, 227, 281, 282 and 287 bytes), which is
what makes every one of them able to detect a mis-anchor.

Three guards and three controls, because a compare that cannot fail proves nothing:

- **Length.** `zip` stops at the shorter side, so a truncated — or empty — dump compares equal as far
  as it goes and would report IDENTICAL (demonstrated: a zero-byte shipped dump passed). Every
  framebuffer is now required to be exactly 32000 bytes on both sides, and our side additionally
  reports the total bytes its dumps wrote (`frame_bytes_written`) so a `savebin` or `Fwrite` that
  silently did nothing is caught rather than read back as a match.
- **Determinism.** The shipped side is run a second time with the identical script and must produce
  identical dumps — it is the side carrying all the machinery, so it is the side whose repeatability
  is worth asserting.
- **A palette fault.** `build.sh framediff-fault && python3 atari/smoke.py framediff-fault` builds
  the identical run with **one pen corrupted on its way to the shifter** and the mode must fail. It
  does, and it fails *on the palette* — `palette 1 DIVERGES on pens [5]`, with the two rows printed
  beneath it showing `131` against `020` — while every bitplane frame still reports IDENTICAL. The
  mode inverts its own verdict, so a detected fault reads as `OK`; it is the run that *passes* the
  comparison which is the failure. That is the check proving it can see the one thing it was added
  for, and it is a separate build because the in-mode controls structurally cannot reach the palette
  (above).
- **A display fault.** `build.sh framediff-skew && python3 atari/smoke.py framediff-skew` misaligns
  the screen by two bytes; the memory comparisons must still pass and the rendered picture must not.
- **A timeline fault.** `build.sh framediff-rearm && python3 atari/smoke.py framediff-rearm` re-arms
  `_colorptr` **every vblank** — what this handler did before push-on-change. Measured: 15 title-phase
  loads and 766 game-phase loads against the shipped binary's 1 and 1, with **778 redundant loads**,
  while `frame`, `palette`, `hw vector` and `rendered` all still report IDENTICAL. That is the whole
  argument for having a timeline compare, made as a control: it is the only surface that moves.
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

### 12. The video base, and why memory-equal is not display-equal

Everything else in this build and its checks compares **memory** — file dumps, `savebin`, the frame
differential. The user does not look at memory. Between the two sits one register, and it is where a
whole class of "it looks wrong" hides:

**An STF's video base register has no low byte.** `$ffff8201` and `$ffff8203` hold bits 23-16 and
15-8; there is no `$ffff820d` (that is the STE's). So an address handed to `Setscreen` that is not
256-byte aligned is **truncated**, and the shifter displays from up to 255 bytes below what the game
is drawing at. Every byte we dump is still correct. ST low-res interleaves plane0..plane3 word by
word, so the displacement's *remainder mod 8* is what you see: a multiple of 8 slides the picture by
whole 4-plane cells, and anything else **permutes the bitplanes** — shapes intact, colours
systematically remapped.

**Section alignment cannot fix it, and the reason is worth being exact about.** The image array
carried `__attribute__((aligned(256)))` and that attribute **worked** — it aligned the array inside
`.bss`. It was simply **irrelevant**: GEMDOS loads a `.PRG` at whatever the TPA gives, and that is
not 256-aligned (measured: `0x12596` under TOS 1.04, `0x1b018` under EmuTOS, for the shipped binary),
so an offset aligned within the image says nothing about the absolute address. The misalignment we
had was exactly the TPA base's own low byte — **24 bytes (a three-cell slide) under EmuTOS and 150
bytes (a six-byte PLANE PERMUTATION, the user's screenshot) under TOS 1.04**. `tos.ld`'s
`SUBALIGN(1)` is about where `.bss` *starts* relative to text+data, which GEMDOS requires; it is not
what defeated the attribute and must not be removed in the belief that it was.

**The fix is a run-time round-up.** The image storage carries 256 bytes of slack and the shim rounds
its base up once, before anything touches it. The cores are untouched — they only ever compute
`image + <Ghidra address>`, and `OS_SCREEN_BASE` stays the constant the host-side differential uses,
so `screen_base` needs no seam.

**And it is asserted every boot.** `Setscreen` is followed by a `Vsync` (TOS applies it from its own
VBL) and then `Physbase()`, and the read-back goes into `STATS.BIN`: *what we asked for* against
*what the hardware says it is displaying from*. Every mode that dumps stats checks they are equal,
and the failure names the fault in its own terms —
`asked the shifter for 0x2e302 but it displays from 0x2e300 — 2 bytes, i.e. 0 whole cells and 2
bytes of PLANE PERMUTATION`.

### 13. The joystick, as far as a headless run can go

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

### 14. Every write to hardware or OS state is read back

Everything §5 through §7 install lands somewhere the differential cannot see: TOS system variables,
KBDVBASE, the VBL queue, the shifter, the IKBD. Three of the four bugs in "The bugs found on target"
reached a green harness for exactly that reason, and the one that did not was `Setscreen`, whose
`Physbase` read-back (§12) caught the base truncation on its first run. §14 generalises that one
pattern to every such write.

**Two words, not one.** `readback_failed` says a write did not take; `readback_attempted` says which
checks *ran*, and `smoke.py` compares it against an **exact mask**, not a floor. A check that quietly
stops executing is indistinguishable from a passing one in a bare fault word — which is how this
project's exit detector spent a year scanning an empty string. The bit names are read out of
`joust_main.c` by `smoke.py` (`readback_bits()`) rather than restated, and a bit the Python side has
not classified as boot-or-teardown is a hard error, so a sixteenth check cannot be added in C and
silently never asserted.

| write site | what is written | assertion | residual blindness |
|---|---|---|---|
| `install_ikbd_vectors` | KBDVBASE joyvec ← `joy_handler` | read the vector back | none — it is RAM |
| `install_ikbd_vectors` | KBDVBASE mousevec ← `null_handler` | read the vector back | none |
| `quiet_conterm` | `conterm` low three bits cleared | read the **whole byte** back against `saved_conterm & CONTERM_KEEP` | none in the check; but `$484` is `0x07` on both ROMs, so a clobber of the byte is unreachable with real data — recorded in `../STATUS.md` |
| `install_vbl_handler` | `_vblqueue` ← our queue | read the pointer back | none |
| `install_vbl_handler` | `nvbls` ← 1 + displaced slots | read the count back | none |
| `install_vbl_handler` | our handler in slot 0 | read the slot back | none |
| `start_ikbd` | IKBD `$15` then `$16` (write-only device) | **proxy**: a reply arrives within 30 vblanks (`ikbd_packets != 0`), which witnesses `$15` accepted, `$16` accepted *and* the vector live | cannot tell a reply from a *correct* reply — the packet's contents are the game's business, and a headless run has no stick |
| `vbl_handler` | `_colorptr` ← the pen table | read the pointer back, then check TOS **zeroed** it one vblank later | witnesses that a load happened, not that the words were right — the hardware-state vector (§11) compares the values |
| `joust_main` | XBIOS `Setscreen` | `Physbase()` (§12) — the read-back this section generalises | none for alignment; an STE honours the low byte, so `smoke.py` asserts the *property*, not just the symptom |
| `shim_teardown` | all five installs restored | read all five back | none |
| `shim_teardown` | IKBD reset `$80 $01` and `$14` | **weakest in the file**: wait for the ACIA's transmit data register to drain, then assert TDRE | two-deep. TDRE means the last byte reached the **shift** register and is still going out (~1.28 ms), so this proves every byte *but the final one* has left; and a byte that does leave says nothing about the controller obeying it. Closed only by the desktop having a mouse afterwards (§13) |

**The interrupt half keeps its own pair of words.** `x |= 1uL << bit` is not interrupt-atomic on the
68000 unless GCC happens to emit a memory-destination `or.l`, and `install_vbl_handler` re-attaches
the handler *before* its own three read-backs — so the two halves really do overlap. A vblank landing
inside that window would drop whichever bit the other half had just set: from `attempted` that is an
intermittent red on a healthy run, from `failed` it is a real fault reading green. The VBL handler
records into `vbl_readback_*` and `dump_stats` ORs the pairs, which removes the window instead of
reasoning about it. Both pairs are `volatile` — the boot dump reads them straight after a `Vsync`
loop the compiler has no reason to think touches them.

Measured on the first run of the sweep: **TDRE is clear when `Ikbdws` returns, every time.** `Ikbdws`
waits for room *before* each byte, so on return the last one has only just been handed to the ACIA —
sampling the flag there tested timing, not delivery. The drain is now waited for. Be precise about
what that buys, though: on a 6850, TDRE goes high when the data register is copied into the **shift**
register, so the final byte is still being clocked out for another ~1.28 ms. `Pterm` can still be
reached with it in flight. The ACIA finishes it regardless, but this assertion does not witness it,
and the limit is recorded in `../STATUS.md`.

**Mutation-tested, because a check that cannot fail is not a check.** Six throwaway mutations, each
rebuilt and re-run, then reverted:

| mutation | caught by |
|---|---|
| joyvec installed with the wrong handler | `RB_JOYVEC_INSTALLED` **and** `RB_IKBD_REPLYING` — a dead vector files no packets |
| `nvbls` restored one short | `RB_NVBLS_RESTORED` |
| `conterm` cleared with the mask inverted | `RB_CONTERM_CLEARED` |
| `_colorptr` never armed | `RB_COLORPTR_ARMED` |
| mousevec left installed at teardown | `RB_MOUSEVEC_RESTORED` |
| `conterm` clobbered to zero | **nothing — and the reason is measured.** `$484` is `0x07` at `joust_main`'s entry on *both* ROMs, so `saved_conterm & CONTERM_KEEP` is 0 and the clobber writes the same value the correct code does. The assertion is exact; the machine offers no data that reaches the difference. Recorded in `../STATUS.md` rather than papered over |

The teardown bits force one ordering change, and it is a **double dump**: `shim_exit` writes
`STATS.BIN` once before the hand-back and again after it. The teardown's read-backs can only exist
after it has run — but a teardown that does not *return* would then take the whole record with it,
and a hung hand-back is exactly what those bits exist to diagnose (`shim_teardown` ends in `Vsync`,
which depends on the VBL queue it has just restored). With two writes, a teardown that never
finishes leaves the first record standing and `smoke.py` reports precisely which read-backs are
**missing**, naming the step that did not complete, instead of "no `STATS.BIN`".

### 15. The timeline: what reached the hardware, in what order

Every other check in this file is a **snapshot**. The framebuffers, the pens, the hardware-state
vector and the rendered picture say what the machine looked like at six instants, and a program that
arrives at the right state by a wildly wrong route passes all of them. **The 773-stomps bug was
exactly that shape**: this handler re-armed `_colorptr` every vblank, 773 palette loads over a run
where the original performs four, every load writing the same correct sixteen words. It was found by
reading a trace by hand. §15 makes it a check.

Both sides' `--trace video_color,psg_write` output is reduced to a **shape per phase**, never to raw
vblank indices — the two binaries do not run at the same speed and are not meant to. Both phase
boundaries are events the trace itself gives, and they are the same events on both sides: the program
starts at its first palette load that is not the desktop's, and the game starts at the first
sound-register write after that — `snd_tone_sweep`'s `reg8=0 reg9=0 reg10=0 reg7=$ff` preamble at the
tail of `init_video`, which is the same event the shim's own `title_over` latches on. Registers 14
and 15 are excluded: they are the **parallel ports**, and port A carries floppy drive select, so a run
that loads a file writes it more than one that does not.

| quantity | ours | shipped | comparable? |
|---|---|---|---|
| desktop palette loads | 1 (EmuTOS) / 2 (TOS 1.04) | same | **equal between the sides**, not pinned to a number |
| title palette loads | 1 | 1 | **equal**, pinned |
| game palette loads | 2 | 1 | **unequal by design** — pinned as the exact pair |
| desktop-restore loads | 1 | 0 | **unequal by design** — pinned as the exact pair |
| redundant loads after the program starts | 0 | 0 | **equal**, and this is the 773 detector |
| game-phase palette TABLES, past our first | identical | identical | **equal**, in order |
| PSG sound writes, `(reg, val)` in order | 14457 | 15237-15937 across runs | **ours is an exact PREFIX of theirs**, with a floor |

The **desktop** row is not pinned to a number and that is measured, not laziness: those loads are
TOS's own, made before either program runs, and EmuTOS loads its desktop palette once where TOS 1.04
loads it twice. A pinned number would have pinned one ROM. The only thing about that phase which
belongs to this comparison is that both sides saw the *same* boot, so that is what is asserted — and
for the same reason redundant loads are counted only from the program's first load onward, since
TOS 1.04's second desktop load is a repeat that neither binary performed.

The two inequalities are disclosed rather than tolerated, and neither is a fudge. The extra **game**
load is the documented one-vblank latency of push-on-change (§5): `cycle_palette` had already written
the attract screen's cycled table into the image, our handler notices on the next vblank and delivers
it just after `snd_tone_sweep` starts, while the shipped binary — pinned into starting a game on its
first attract pass — never re-issues that one. The game palette that follows is identical on both
sides and the hardware vector agrees at every anchor. The extra **restore** load is our run quitting
and handing the desktop palette back; the shipped side is stopped by `--run-vbls` mid-game and never
restores anything. Both are pinned as exact numbers rather than as an inequality, because both sides
are deterministic here and a tolerance is where a regression hides.

Counting loads is not enough on its own, so the **tables** are compared too: past our one extra
load, our game-phase palettes must be the shipped binary's, in order. Without that, a regression
that dropped the latency load and gained a stray re-arm somewhere else still counts 2 and reports
"as pinned" — a green on the one surface built to catch exactly that. Naming *where* our extra load
is (`OUR_EXTRA_GAME_LOADS = 1`, and it is the first) is what turns the `(2, 1)` pair from a count
into a structure.

Both phase boundaries are **asserted, not assumed**. The game boundary must be `snd_tone_sweep`'s
literal preamble — `reg8=0 reg9=0 reg10=0 reg7=$ff` — so a stray mixer or port-direction write from
disk I/O landing there fails loudly instead of silently reclassifying a title load as a game load.
And every palette load before the program's first must carry the *same* table: TOS 1.04 loads its
desktop palette twice, and if a boot ever loaded an intermediate first, the "first non-desktop load"
anchor would latch onto TOS's second load and shift every count by one.

The PSG comparison is a **prefix** for a structural reason, not as a slack: our `framediff` build
stops itself at the last sample frame while the shipped side runs on to `--run-vbls`, so its stream
is strictly longer. Every write we do make is the same write it made, at the same point in the
sequence — all 14457 of them. A prefix alone is satisfied by a stream of length one, though, so
there is a **floor**: fewer than `MIN_PSG_WRITES` fails. Nothing else in `framediff` looks at the
PSG, and the shim's own counter measures what the game *asked for*, not what reached the chip.

The traced run is given the **shipped side's vblank budget**, not the default 20000. At the default
our build spends ~19,000 vblanks sitting on the TOS desktop after its own `Pterm`, and any palette
load TOS makes in that tail lands in the `restore` phase this table pins at exactly one.

### 16. The play build in the smoke matrix

Everything else here runs a build with something *added* for the harness: a scripted key, a frame
limit, an injected fault. `smoke.py play` runs the configuration a person actually plays — real
console, real joysticks, no limit, no fault. The only difference from `build.sh play` is that it
writes `STATS.BIN` once, at boot: a build with no scripted key and no frame limit never reaches
`shim_exit` under a headless run, so its read-backs would otherwise be unobservable in the shape
people run it in.

That "only difference" is a claim, so it is made true rather than asserted: `SMOKE_BOOT_DUMP` also
switches the **progress beacons off**. A beacon is a GEMDOS `Fcreate`/`Fclose` pair, and nine of them
interleaved with the very installs being read back is real disk I/O `build.sh play` never performs.
A boot fault that depends on *not* doing it — and this project already has a recorded GEMDOS handle
gotcha — would hide behind them, which would make the certified boot a different boot from the one
being certified about.

It asserts the **boot** read-back sweep (nine of §14's fifteen — the six hand-back bits are absent,
and the mask is exact, so a run that somehow *did* tear down here would also fail) and the
**hardware-state vector at the title screen**, captured at a vblank boundary anchored on the 200th
title-screen console poll: ST low resolution, and sixteen pens that are neither still the desktop's
nor degenerate (all sixteen equal is what a blank screen looks like from here, and "not the
desktop's" alone would call that a pass). That is a **shape** assertion, not a value one, and §14's
table in `../STATUS.md` records it as such: the *right* pens are pinned for the `framediff` build by
two surfaces at six anchors, and carrying that reference into this mode would need a second binary
running beside it. The desktop's pens come from the **same boot** — a second anchor on `joust_main`
itself, before any install — rather than from a second run or a written-down table: they differ
between EmuTOS and TOS 1.04, and a reference from a different boot is only as good as that boot
being identical, which is the assumption this whole file exists to stop making.

**And then the run is killed, which is stated rather than glossed.** The program is sitting in
`title_screen`'s console poll waiting for a key that will never come, so `--run-vbls` expires with it
still resident and still hooked into TOS. The **exit status** is therefore not asserted — it would be
asserting that a program we never let finish shut down cleanly. The **log scan** *is* applied, to
both boots: `check_exit` was two independent assertions wearing one name, and only the return-code
half is inapplicable here. The fault-and-halt scan applies to any run at all, and it is the surface
that sees the class Hatari survives — leaving it out would have made this mode blind in exactly the
way the half-blind exit detector was. **Boot health is asserted for this build; exit health is not,
and cannot be without giving it a scripted key, at which point it is no longer the play build.** The
exit path is covered by `quit`, `quittitle` and `restart`, which run the same `shim_teardown` through
the same `shim_exit`.

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
- **One title-screen palette load the original never shows.** `title_attract_pass` rotates the six-pen
  ring *before* its console poll, so with the key taken on the first poll our pusher hands TOS the
  rotated table for one vblank. The shipped binary computes the same rotation but its `Setpalette` is
  superseded within the same vblank and never latches, so its timeline goes straight from the raw
  table to the game palette. One frame of slightly different title hues; the pinned timelines are
  otherwise the same shape (ours 6 loads, its 4).
- **The name-entry screen's colour flash is missing.** `flash_hiscore_color` computes the flashing
  pen and *returns* it — XBIOS `Setcolor` writes hardware, so the kit models it as a no-op and the
  reconstruction has nothing to issue. The shim does not re-issue it either, so pen 10 sits still
  where the original pulses it. §5's push-on-change is what makes re-issuing it possible at all (the
  old per-vblank stamp would have erased it), but the call itself is still owed — the same shape as
  the `Ikbdws` and `Setpalette` omissions in §5/§6.

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
