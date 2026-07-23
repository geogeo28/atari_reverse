# render/atari — run the remaster HUD on a real 68000 (Hatari)

remaster renders only the HUD so far, so this cross-compiles `rm_draw_hud` to 68000 and runs it as
a GEMDOS `.PRG` under Hatari — proving the remaster C is correct not just on the host, but compiled
and executed on an independent 68000.

Because the HUD reads asset tables (font, colour-fill table, mask/cursor tables, the gauge string,
the dashboard graphic and the variant sprites from `buf_c`) that normally come from the recreate
loaders, we **capture them once on the host** (`gen_hud_fixture.py`, via the same `adapter.py` the
equivalence tests use), bake them + the `HudState` into `build/hud_fixture.h`, and draw the HUD over
a **blank screen** on-target — rendering only what remaster's C implements (no captured game frame).

## The proof

`gen_hud_fixture.py` also writes `build/golden.bin` — recreate's `g_draw_hud` on the same blank
screen. The demo dumps its painted framebuffer to `C:\SCREEN.BIN`; `run_hatari.py` byte-compares
that against `golden.bin`. A **MATCH** proves remaster's HUD, cross-compiled and run on a real 68000,
is pixel-identical to the verified recreate cores. (recreate's HUD is itself verified byte-for-byte
against the Musashi oracle, so this closes the loop end to end.)

## Pieces

| file | role |
|------|------|
| `gen_hud_fixture.py` | capture background + assets + `HudState` + golden + palette from the host harness |
| `main.c`             | TOS shim: build the structs from the fixture, `rm_draw_hud`, dump `SCREEN.BIN`, set palette, blit, wait for a key |
| `os.s` / `tos.ld` / `mkprg.py` | GEMDOS entry + trap wrappers, link script, `.PRG` wrapper (copied from recreate's harness) |
| `shim_include/string.h` / `shim.c` | freestanding `<string.h>` decls + defs, linked by every on-target program (bare-metal GCC has no libc) |
| `build.sh`           | generate fixture → cross-compile `hud.c`+`text.c`+shim → `.PRG` → stage `disk/` |
| `run_hatari.py`      | headless: run the `.PRG`, byte-compare `SCREEN.BIN` vs `golden.bin`, write a PNG |
| `run.sh`             | interactive: watch it in the Hatari GUI |
| `gen_game_fixture.py` / `game_main.c` | the on-target BuggyBoy game (below): non-asset-file fixture + the game shell (leg select → race → between-legs flow) |
| `build_game.sh` | build `BUGGYBOY.PRG` (the shipping game) or, with `GAME_PRG`/`GAME_EXTRA_CFLAGS`, a variant |
| `run_golden.py` | the frame-0 golden harness: build the `GOLDEN.PRG` fast-path variant + byte-compare its leg-0 boot frame vs recreate |

## Use

```bash
cd projects/buggyboy/recreate && make build/libbuggyboy.so   # once: the fixture generator drives it
cd ../remaster
bash render/atari/build.sh                 # -> build/HUD.PRG + disk/HUD.PRG
python render/atari/run_hatari.py          # headless: prints MATCH, writes out/render/remaster_hud_hatari.png
bash render/atari/run.sh                   # watch it in Hatari (press a key in the ST to exit)
```

Hatari needs a 4 MiB machine (`--memsize 4`); `build/` and `disk/` are gitignored build artifacts.

## The game (`BUGGYBOY.PRG`)

`BUGGYBOY.PRG` is the playable game: it boots into the **leg select** — the course map plus the
5-entry **leg-name menu** (`rm_draw_panel5`) — and fire starts the chosen leg through the "get ready"
screen (the results + menu frozen while the leg-start palette flashes, the dashboard **place-name
labels** (`rm_draw_leg_labels`) drawn on for the race that follows — they are NOT on the interactive
select screen, only the get-ready and the Phase-B attract demo). The whole outer loop (leg select → race → leg end →
highscore [name entry] → intermission attract cycle → back to the leg select) runs on a real 68000. It ships
**without sound** — the sound path is a documented, unported seam. When a race ends with a score that makes
the leg's high-score table, the **name-entry screen** runs (`rm_flow_name_entry`): Up/Down/Left/Right dial
each of the three initials (Up/Left step a letter back, Down/Right forward) and **Space** (fire) confirms
one — a 30-second `TIME` countdown ends entry if it runs out; a score that misses shows a short game-over
screen instead. The controls are **identical to the original arcade port** (the one deliberate
deviation is Q, below):

| Key | Race | Leg select | Name entry |
|-----|------|------------|------------|
| Up / Down | throttle / brake | previous / next leg | dial initial back / forward |
| Left / Right | steer | previous / next leg | dial initial back / forward |
| Space | fire (dashboard variant) | start the selected leg | confirm an initial (on '`' backs up) |
| Joystick (port 1) | steer + throttle/brake, button = fire | nav + button starts the leg | dial + button confirms |
| F1..F5 | — | select + start that leg | — |
| G | toggle the dashboard-variant display (`dsp_toggle`) | — | — |
| **ESC** | **abort back to the intermission** | — | — |
| Q | quit to the desktop *(the one deviation)* | quit to the desktop *(the one deviation)* | — |

**ESC** during a race does exactly what the original does (`main @0x10100:286` `cmpi.b #$1b,d0 / beq`):
it breaks the race loop straight into `update_highscore` → the intermission attract cycle → the leg
select — the leg ends immediately, its current score is ranked, no bonus tally. **Q** is the *single*
deliberate deviation from the original: the arcade is a coin-op whose `main` is an infinite loop that
never terminates, but a GEMDOS `.PRG` needs a way back to the desktop, so Q — a key the original never
reads — quits. The original has **no** quit and **no** restart key, so the shell's earlier R-restart and
`Esc`-quit are gone.

A joystick in **port 1** works everywhere the driving keys do and has **priority**: whenever the stick
reports any direction or the fire button, it wins and the keyboard is ignored; the keyboard is the
fallback only when the stick is centred (`read_input @0x120b0`). F1..F5, G, ESC and Q stay keyboard-only
(the arcade has no joystick equivalent). The leg-select arrow-key navigation is the one *non-conflicting*
convenience the shell keeps that the arcade's `init_playfield` reads only from the stick — it collides
with nothing (F1..F5 are the arcade's keyboard way to pick a leg) and keeps keyboard-only play usable.

The whole Phase-A render pipeline is driven by the ported **player physics** — you drive
the buggy. Each frame is game_update-then-draw, as the original orders it:

1. `rm_player_update` (`src/player.c`) — the driving model: throttle → engine rpm → speed, speed →
   the road-scroll rate and the **view advance whose wrap advances the course**, steering → wheel
   position → body lean and road curvature, and the road-edge clamp / off-road push. Its outputs are
   fanned out to the render structs (`apply_player`), which is all the game loop is beyond this.
2. `rm_gobj_prefix` (off-frame state) → `rm_build_road_geometry` (from the current pose) →
   `rm_render_road` → `rm_blit_road_scroll` (the scrolling near-road band + sky) → the
   `draw_game_objects` tree (`rm_draw_ground`, `rm_draw_fg_sprite`, the two roadside
   `rm_draw_object_list` passes split around the scaled `rm_draw_object`, and `rm_draw_buggy` ordered
   against the fixed pass by the view) → `rm_draw_hud`, and flips.

```bash
bash render/atari/build_game.sh            # -> build/BUGGYBOY.PRG + disk/BUGGYBOY.PRG (shipping: boots the leg select)
python render/atari/run_golden.py          # frame-0 golden harness: builds GOLDEN.PRG (-DGOLDEN_BOOT_LEG=0), prints MATCH
hatari --memsize 4 --tos-res low --harddrive render/atari/disk --auto 'C:\BUGGYBOY.PRG'   # play it
```

The shipping `BUGGYBOY.PRG` boots into the leg select, so it has no deterministic first frame to pin;
`run_golden.py` therefore builds a SEPARATE variant, `GOLDEN.PRG`, compiled with `-DGOLDEN_BOOT_LEG=0`,
that skips the leg select and starts leg 0 directly — dumping that leg-start frame *before* any physics
so it can be byte-compared to recreate's pipeline. **Legs 1–4 are playable, but only leg 0 has a
golden** (a per-leg golden is deferred).

Controls (**held** keys — the original arcade scheme; see the table above): **F1..F5** select + start a
leg (leg-select screen), **↑/↓** throttle / brake, **←/→** steer, **Space** fire (cycles the dashboard
variant, as in the original), **G** toggles the dashboard-variant display, **ESC** aborts a race back to
the intermission, **Q** quits to the desktop (the one deviation from the original).
**The game loads the game's own data files.** `COURSES.DAT` and `GRAPHICS.GRA` ship on the disk
beside `BUGGYBOY.PRG` and are read + unpacked at boot by `src/assets.c` (see `include/assets.h`). Both
reads are bounded by the arena and the unpack itself is bounded at both ends, so a missing,
truncated or foreign file is refused rather than walking the decode off the end of the arena. The
game then names the file on the ST console and exits — note that under *headless* Hatari that
console is invisible, so the only symptom a script sees is a missing `SCREEN.BIN`. With both
present, the road texture, the scroll playfield, the
leg's packed course stream, the object record arena and every sprite are the real thing.
`gen_game_fixture.py` therefore bakes only what is *not* file content —
the original program's own data-segment tables (fonts, colour pairs, road param/edge tables, the
geometry const sources, the STATIC+bss blob the object dispatcher reads), the initial
pose/scroll/course state and the palette — into `build/game_fixture.h`, plus the `ARENA_*` offsets at
which the arena-resident assets live. Under `GEN_GOLDEN=1` (set only by `run_golden.py`) it *also*
writes `golden.bin` (recreate's `g_build_road_geometry` + `g_render_road` + `g_blit_road_scroll` +
`g_draw_game_objects` + `g_draw_hud` for the same pose, rendered from a freshly-loaded arena so both
sides see identical assets) and `palette.bin`; a plain shipping/bench build leaves the flag unset and
skips that heavy render, since only `run_golden.py` compares against it.
`run_golden.py` byte-compares that GOLDEN.PRG variant's first frame — drawn *before* any physics runs — against it; a
**MATCH** proves the whole ported pipeline is pixel-identical on a real 68000. The physics driving it
is validated on the host against recreate's `g_game_update` (`test/test_player.py`), as are the
geometry and course advance (`test/test_geometry.py`, `test/test_course.py`).

### Held keys: the game takes the IKBD interrupt

GEMDOS reports key *presses*; driving needs to know which keys are *held*, and several at once
(throttle plus steering), plus the joystick. So the game installs its own handler on the IKBD ACIA
interrupt (MFP channel 6, vector `0x46` @ `0x118`) after switching **mouse** reporting off (joystick
reporting is left **on**). The ACIA now delivers two kinds of message, so the `os.s` handler is a small
packet state machine: a keyboard make/break is a single byte `< 0xF6` (break codes top out at `0xF2`) —
"bit 7 clear → down, set → up" into a 128-byte `key_down[]` table; an IKBD **report** is a header
`0xF6..0xFF` plus a fixed payload, and a joystick report (`0xFD`) routes its payload into `joy_state`
(any other report's payload is swallowed so it never lands in `key_down[]`). `read_input` interrogates
the sticks once a frame with IKBD command `0x16` — via `Ikbdws` (XBIOS), because this shell is a
*user-mode* GEMDOS program where the ACIA is supervisor-only, whereas the arcade port (which pokes the
ACIA directly, `read_joystick @0x12110`) ran supervisor. The old vector and the mouse mode are restored
on exit. The first-frame dump happens *before* the install, so the headless MATCH run never depends on it.

### Aliased globals the game has to model

recreate threads one flat image, so several logically-separate tables share an address. The game keeps
them separate and must reproduce the aliasing explicitly — each of these caused a real on-target diff:

| Alias | Effect |
|-------|--------|
| `anim_color` == `fuel_mask` (`0x17f08`) | the prefix's animated colour **is** the HUD's phase-6a fuel mask, so both point at one mutable buffer |
| `obj_xoff_tbl` == `road_width_tbl + 2` (`0x18f26`) | the object dispatcher's x-offset table is the freshly built control table, so it is rebound to `ctrl` each frame |
| `ground_view_off` == `obj_scan_off` (`0x18c58`) | the ground's view column and the object list's scan offset are one value (`view_flags * 0xdd`) |

`draw_game_objects` also writes off-screen sprite fragments well past the visible 32000 bytes, so each
screen buffer carries a `SCREEN_OVERDRAW` tail (in the original the draw buffer is followed by ample
RAM). Two debug build flags: `GAME_EXTRA_CFLAGS=-DGAME_DUMP_STAGE=N` cuts the frame short after stage
N (0 road, 1 ground, 2 foreground, 3 pass 1), so the dump holds a partial frame — that is how an
on-target divergence gets bisected to a single stage. `-DGAME_AUTODRIVE=N` replaces the keyboard with
a fixed input script and dumps the frame after N frames, which is how the *loop* (physics → course
advance → render, on the 68000) gets checked headlessly rather than only frame 0.

Scope note: the throttle scrolls the course's authored **segment slopes** (`seg_data`) through the
geometry builder, and `build_road_geometry` integrates them into the per-row road offset — so the
road's hills and left/right curvature stream from the leg's packed course as you drive, on top of the
player's own `road_curve`. Section 12's object / marker ring is ported too, so the road's per-band
flags now stream with the course; the crash / auto-steer script runs once something arms it.

The roadside scenery streams along the course too: `draw_object_list`'s flag streams,
`draw_ground`'s markers, the sprite-slot count and the buggy/foreground sprite gates all derive
from the live ring (`src/course.c`'s `rm_ring_*` helpers, refreshed after every course advance and
on a restart) — see PORTING.md's "the ring's consumers are unified".

What the game still leaves as a seam: **sound** (INITTUNE/INITFX/TURNOFF + the VBL vector — the game
ships without it), and the record-driven mode-2/4/6 palette / screen-offset events in
`course_advance`'s tail. The course-event engine that *decides* to crash you (the collision probe, the
fx block and the horizon-event dispatch) is ported and wired, so the game arms its own crashes and
delivers its own checkpoint / finish / bonus events — see STATUS/PORTING.

The alignment gotcha: the cores read the baked tables with `be16`/`be32` (word/long moves), which
fault on an odd address on the 68000, so the fixture arrays and the BSS scratch are `aligned(2)`.

## Scope

`HUD.PRG` is the HUD-only proof (rendered over a blank screen, no captured game frame — `run_hatari.py`
pins it). `BUGGYBOY.PRG` is the whole playable game: the render pipeline (road, scroll, the object tree,
the HUD) driven by the ported physics and the between-legs flow, everything drawn by remaster's own C.
`run_golden.py` pins its leg-0 boot frame byte-for-byte against recreate's pipeline; the rest of the
loop is guarded by the host equivalence suite (`make test`) and the on-target flow trace. The remaining
seam is sound.
