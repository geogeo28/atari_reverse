# Three concepts — original Wolf3D-class raycaster, stock Atari STE

Author's note: I've shipped 16-bit first-person games. Everything below is designed *from* the
brief's numbers outward, not decorated onto them. Three concepts, deliberately spread across the
risk curve: one safest, one most atmospheric, one highest ceiling.

## Shared assumptions (all three concepts inherit these)

**The real frame budget is 3 VBLs, not 1.** 16.7 fps = 480,000 cycles per rendered frame. My
working allocation, to be held as a target and measured in Hatari:

| Stage | Cycles | Note |
|---|---:|---|
| DDA cast, 160 rays | 55,000 | grid-stepping, no per-ray divide (reciprocal LUT) |
| Wall columns → chunky byte buffer | 150,000 | unrolled, 16 height-class routines |
| Billboard sprites (6 max on screen) | 70,000 | back-to-front, clipped by the column depth array |
| c2p + pixel-double → 320x200 | 120,000 | table-driven, 160x100 bytes in / 32,000 bytes out |
| AI, doors, audio, HUD, input | 60,000 | |
| Slack | 25,000 | |

80-column low-detail mode halves the first three → 2 VBLs → 25 fps. Double-buffered (2x32,000 B),
one 16,000 B chunky buffer, ~64 KB of c2p tables.

**Distance shading is baked, never computed.** Each 64x64-nibble wall texture ships in **5
pre-shaded depth bands** (2,048 B x 5 = 10,240 B per texture; 8 textures = 80 KB per level set;
3 sets cover 8 levels). Band index = `depth_band + is_north_south_face`, so the lit/unlit side cue
costs *one add*. Beyond the last band the column is a **flat fill of the ramp's terminus colour** —
far geometry is a `movem.l` fill, not a texture map. Fog is therefore free *and* it is what makes
the frame budget close.

**Renderer red lines, all three:** no floor/ceiling textures (flat fills), no transparent walls
(grates are opaque textures with black holes painted in), no outdoor areas, no variable floor
height, no angled walls. Doors are thin sliding walls animated by texture X-offset.

**Sample budget is 8.0 seconds.** 12,500 B/s x 8 bit = 100 KB is eight seconds of audio, total, for
the whole game. Every concept below lists its ten sounds with durations that sum to ~8 s.

---

# 1. HADAL

**Pitch:** *You have forty minutes of air and eight flooded decks between you and the surface — and
the dark down here is looking back.*

**Setting & tone.** Rig 9, a deep-shelf drilling platform, 1,100 m down, gone silent. You are the
salvage diver sent to recover the core samples. Everything is submerged. Tone: cold procedural
dread — no jump scares, just an air gauge.

**Player fantasy.** The competent professional in a suit that is slowly failing. Not a soldier.

**Palette strategy — one hue-shifting atmospheric ramp.** The 16 colours are: **black (#000000)**,
a **9-step ramp that shifts hue as it darkens**, and **six accents**. The ramp runs from your
lamp's warm bone-white to the water's indigo:
`#FFEEBB, #DDCC99, #AABB88, #77AA88, #559988, #338877, #227766, #114455, #001133`.
Accents: `#FF3311` alarm/blood, `#FFCC00` amber key-glow, `#66FFEE` bioluminescence,
`#886644` corroded steel, `#DDDDEE` glass/bubble specular, `#442233` sprite under-shadow.
**Why 16 looks intentional:** underwater light *is* low-chroma and monotone-converging. A diver's
lamp genuinely turns warm-near/blue-far. The palette isn't a limitation, it's a water column. The
ramp terminus `#001133` doubles as the flat far-fill *and* the ceiling colour, so the world visibly
dissolves into itself.

**Art at 160x100.** Rig interiors: fat pipes, hatch wheels, rib frames, hazard chevrons. Big
silhouettes, no fine detail — everything is 4-px-and-up features, which reads perfectly doubled.
8 wall textures/level: plate steel, ribbed bulkhead, pipe run, hatch, grate (opaque), warning
chevron, tile, coral-fouled plate.

**Enemies (4).** *Scuttler* — crab-thing, walks straight at you, melee, fast, arrives in threes.
*Lure* — anglerfish; only its light is visible past band 2, drifts in, ranged bio-shock. *Drowned
crewman* — old hardsuit, slow, hitscan speargun, breaks line-of-sight at corners. *The Bell*
(act boss) — a diving bell on limbs, stationary, sweeping sonar cone, must be flanked.
4 view angles for the crewman, 1 for the rest. 6 sprites max on screen, 48x48 source.

**Weapons.** *Bolt gun* (harpoon; reliable, single target, recoverable bolts) and *cutting torch*
(short cone, melts armour, consumes fuel *and* air). Two, both diegetic to the fantasy.

**Pickups.** Air cylinders (the clock), bolts, torch fuel, three keycards (amber/cyan/red — mapped
to the three accent entries so the HUD icon and the door light are literally the same colour word),
sonar beacons (one-shot map ping).

**Core loop / progression.** Enter a flooded section → air timer runs → find the section key →
cycle the airlock → **timer resets, and that's your only checkpoint**. 8 decks, 32x32 typical,
48x48 for the moon-pool level. ~28 minutes. Win: reach the surface bell. Lose: air at zero.

**STE hook.** Cutting a deck's power is a **palette-only event** — the whole ramp shifts from
lamp-warm to emergency-red over 24 frames, zero render cost, and it re-tints every texture on
screen. Damage = hardware fine-scroll jitter (screen shake for free) + a one-frame palette flash.
Raster split at line 160 gives the HUD its own 16 colours. DMA one-shot sonar ping as a stinger.

**Audio.** YM: two channels of slow detuned drone, third channel a five-note sonar figure every
~9 s; hull groans via the YM envelope generator as a pitched buzz. Samples (8.0 s):
bolt-gun thunk 0.35 / torch loop-cell 0.60 / air-hiss warning 0.70 / hatch cycle 1.10 /
scuttler chitter 0.45 / crewman speargun 0.30 / deep whale-call 1.60 / player hurt 0.40 /
keycard chime 0.25 / drowning heartbeat 0.80 = **6.55 s**, 1.4 s spare for a boss roar.

**Risks & how the design dodges them.** *Caustics on the floor* — cut; a slow 2-entry palette cycle
on the ceiling colour sells moving water for nothing. *Floaty creatures* need per-sprite vertical
billboard offset — that is the one renderer extension I accept (one add per sprite, sells water
better than anything else). *Visual sameness* is the real risk: eight steel decks blur together.
Mitigated by giving each act a distinct ramp tint (green algae act / red emergency act / blue deep
act) — again palette-only, no new art.

---

# 2. BLACK ICE

**Pitch:** *Break into a dying mainframe, strip it for data, and get out before the trace finds
your body.*

**Setting & tone.** 1987-as-imagined-in-1987. You are a repossession runner walking a corporate
mainframe's memory map as physical space. Dry, deadpan corporate humour in the mission text;
absolute cold in the world itself.

**Player fantasy.** The intruder with a clock. Speed and route knowledge, not survival.

**Palette strategy — two opposed chroma ramps on a black void.** Cyan = infrastructure you can
use; magenta = ICE that wants you dead. That is the entire visual language and it is legible in one
glance at 160x100.
Void `#000000`. Cyan ramp: `#CCFFFF, #77EEFF, #33BBEE, #1177BB, #003355`.
Magenta ramp: `#FFCCFF, #FF77DD, #DD33AA, #991177, #440044`.
Accents: `#FFFF66` data, `#FFFFFF` edge/muzzle, `#33FF66` integrity, `#FF4400` alarm,
`#333344` horizon grid line.
**Why 16 looks intentional:** the world is *rendered by the machine you are inside*. Flat panels,
hard edge trim, and exactly sixteen registers is the diegesis. Nobody reads this as "the ST could
only do 16" — they read it as Tron.

**Art at 160x100 — and this is the cheapest concept by a mile.** Floor and ceiling are `#000000`,
which is not a compromise, it is the point: the void. Wall textures are geometric (circuit lattice,
hex mesh, glyph column, bus trunk, firewall chevron, corrupted-sector noise, anchor pylon, exit
gate) — procedurally generated in Python, RLE-compressible to near nothing, and *authored in an
afternoon*. Depth fog to black means aggressive far-clipping is diegetic, so this concept holds
160 columns at 3 VBLs with slack, and is the only one I'd try 200 columns on.

**Enemies (4).** *Watchdog* — walks straight at you, melee zap, cheap, packs of four. *Sentry* —
turret embedded in a wall panel, hitscan, only vulnerable when its firing iris is open. *Tracer* —
fast, strafes and circles, ranged, flees to raise the alarm (kill it or pay for it). *Black ICE*
(final boss) — mirrors your movement across the room's axis, teleports between four anchor cells;
you win by shooting the anchors, not the boss.

**Weapons.** *Buster* (fast, weak, infinite floor) and *Spike* (slow, pierces every enemy in a
corridor — a grid map makes piercing genuinely tactical).

**Pickups.** Cycles (ammo), integrity (health), three access tokens, trace-scrubbers.

**Core loop.** A rising **trace meter**. Alarms and time raise it; killing tracers and scrubbers
lower it. Reach 100% and the ICE *hardens*: the magenta ramp shifts hot, enemies gain a tier, and
you must exfil to the entry gate. 8 sectors, 32x32 to 48x48, ~22 minutes — the fastest game of the
three, built for replay and a route timer on the results screen.

**STE hook.** The trace escalation is **a palette ramp animation and nothing else** — the world
turns against you at zero render cost. Raster split gives the HUD a second 16 colours so the trace
bar can use hues the world doesn't own. STE enhanced-port pad: separate fire/strafe/use buttons.
DMA stingers on trace thresholds (25/50/75/100%).

**Audio.** YM: driving 140 BPM two-channel bassline + arpeggio, tempo steps up at each trace
threshold (the music *is* the timer). Samples (8.0 s): buster shot 0.20 / spike 0.35 /
watchdog snarl 0.30 / sentry charge 0.45 / gate open 0.55 / token grab 0.25 / trace alarm 0.90 /
player hit 0.30 / enemy dissolve 0.40 / exfil siren 1.20 = **4.90 s**, ~3 s spare for a sampled
title-screen vocal hit and boss sounds.

**Risks.** Lowest renderer risk of the three — no transparency, no outdoors, no floor art, flat
fills everywhere. The real risk is *aesthetic*: an all-geometric world can look like a tech demo
rather than a place. Mitigation is layout craft (memorable landmark rooms, the corrupted sectors as
visual set-pieces) and heavy use of the yellow/green accents for hand-placed detail. Second risk:
neon cyberspace is the most familiar of the three themes.

---

# 3. MISERERE

**Pitch:** *Sealed inside a plague abbey with a lantern, a wheellock and a limited amount of oil —
and the dark is where the things that matter live.*

**Setting & tone.** Saint Bartle's Abbey, the year of the second pestilence. You are a corpse-warden
hired to burn the dead; the brothers dug something up in the crypt. Tone: grim folk horror, told in
the visual language of a **German broadsheet woodcut**.

**Player fantasy.** A frightened professional with two shots and one flame, deciding how much of the
world he can afford to see.

**Palette strategy — printed inks, not colours.** A 8-step paper→ink ramp, a 4-step candle ramp, and
4 accents.
Paper/ink: `#FFEEDD, #EEDDBB, #CCBB99, #AA9977, #776655, #443344, #221122, #000000`.
Candle: `#FFCC55, #EE8822, #BB4411, #661100`.
Accents: `#AA0022` blood (the one saturated hue in the game, hand-tinted-broadsheet style),
`#667755` plague verdigris, `#DDCCEE` cloister moonlight, `#554433` leather/wood.
**Why 16 looks intentional:** this is a *print*. Two inks plus hand-tinting is historically exactly
right, and chunky doubled pixels read as a coarse woodblock rather than as low resolution. Low res
*helps* this style — it is the only one of the three where I'd argue 160x100 is an artistic asset.
Lit/unlit is warm-vs-cool (your lantern's candle ramp vs the paper ramp), which is a far stronger
readability cue than one shade step.

**The mechanic that makes this concept: the lantern is the draw distance.** Turn it up and you see
5 depth bands and everything sees you. Turn it down and you see 2 bands, move silently, and — the
part that matters — **the renderer draws fewer textured columns and the frame rate goes up**. The
engine's single hardest limit is converted into the core tension and into a performance dividend in
exactly the moments the game is most dangerous. Oil is the resource. This is what "designed for the
constraints" means.

**Art at 160x100.** Heavy black outlines, hatched shading, bold silhouettes. Hatching is generated
procedurally in Python (it is line-drawing maths, not hand pixel-pushing) and is baked only into the
two nearest depth bands — far bands are flat, which kills scaling shimmer *and* saves work.
8 textures/level: ashlar, plaster with a painted saint, bookcase, ossuary bone-stack, oak door,
barred cell, mossed crypt stone, stained window (opaque, palette-animated).

**Enemies (4).** *Flagellant* — walks straight at you, melee flail, does not flinch, moans (you hear
it before you see it). *Bell-brother* — blind, hunts by sound; ignores you if you walk instead of run
with the lantern low; rings a bell that summons flagellants. *Censer-thrower* — ranged, lobs a slow
burning arc, keeps distance, telegraphs. *The Abbot* (final boss) — a tall thin silhouette that
**only advances while your lantern is out**; the fight is conducted by muzzle flash.

**Weapons.** *Wheellock pistol* — one shot, ~2 s reload, enormous impact; the reload is the horror
pacing device. *Fire-pot* — thrown, area denial, burns for ~4 s (palette-animated flicker, no extra
sprite work). *Billhook* — silent melee, for when you can't afford the noise.

**Pickups.** Powder & shot, lamp oil, three keys (crypt/refectory/tower), and **relics** — small
permanent upgrades (faster reload, slower oil burn, a third fire-pot) that give the 8-level run a
progression spine.

**Progression.** Gatehouse → Infirmary → Refectory → Cloister → Scriptorium → Crypt → Ossuary →
Bell Tower. 32x32 typical, 48x48 crypt. ~35 minutes, the longest and slowest-paced of the three.
Win: ring the tower bell. Lose: death (no timer — the resource is oil, not time).

**STE hook.** Lantern brightness is a **live palette ramp interpolation across the 4096-colour
gamut** — the world dims smoothly through intermediate colours the ST simply cannot produce, and it
costs 16 register writes in the VBL. Muzzle flash = one-frame full-palette lift. Damage = hardware
fine-scroll shake. Raster split for a parchment-styled HUD with its own 16 inks.

**Audio.** YM: almost no music. Long silences, a solo three-voice *organum* motif on entering a new
wing, and a single held drone under the crypt. Restraint is the score. Samples (8.0 s):
wheellock crack 0.55 / reload ratchet 0.70 / fire-pot whoosh 0.50 / flagellant moan 0.90 /
abbey bell 1.30 / door groan 0.85 / footstep-on-bone 0.25 / player hurt 0.45 /
match strike 0.30 / choir whisper sting 1.10 = **6.90 s**, 1.1 s spare.

**Risks.** Highest art effort — mitigated by the fact that engraving hatching is *algorithmic*, and
the brief already mandates Python/PIL asset scripts. Hatching shimmer under scaling — mitigated by
restricting hatching to the two near bands. Very dark scenes on a real CRT/RGB monitor can crush to
mud — mitigated by never letting the near band go below `#443344` and by pinning a calibration
screen at first boot. No transparency (stained glass is opaque + palette-animated), no outdoors
(the cloister is roofed by design — a covered arcade), no floor art.

---

# Comparison

| | **HADAL** | **BLACK ICE** | **MISERERE** |
|---|---|---|---|
| **Theme** | Deep-sea salvage horror, flooded rig | Cyberspace heist inside a dying mainframe | Woodcut folk horror, plague abbey |
| **Palette strategy** | 1 hue-shifting 9-step ramp (warm lamp → indigo water) + 6 accents; ramp terminus = fog, ceiling and far-fill | 2 opposed 5-step chroma ramps (cyan = safe / magenta = ICE) on a black void + 5 accents | 8-step paper→ink ramp + 4-step candle ramp + 4 hand-tint accents; lit/unlit = warm vs cool |
| **Renderer risk** | **Medium** — wants floating sprites (accepted: 1 add/sprite) and caustics (cut, faked in palette) | **Low** — flat black floor/ceiling is the aesthetic; geometric textures; only concept I'd push to 200 columns | **Medium** — hatching shimmer under scaling; solved by near-band-only hatching + flat far bands |
| **Art effort** | Medium — 3 texture sets, 4 enemies, 1 with 4 view angles | **Low** — procedurally generated geometric walls, RLE-tiny, authored in a day | **High** — but the style is algorithmic (procedural hatching), which is exactly what the PIL pipeline is good at |
| **Memorability** | The air gauge, and fog *as* the monster | The trace meter turning the whole world magenta | The lantern: darkness as an inventory item, and a look no ST game has |
| **Length / pace** | ~28 min, tense-methodical | ~22 min, fast, replay/route-timer | ~35 min, slow, deliberate |
| **Pick this if** | You want atmosphere with predictable production risk | The team is one programmer with no dedicated pixel artist | You want the game people still talk about in 2035 |

# Ranked recommendation

**1. MISERERE.** It is the only one of the three where the engine's single worst limitation — draw
distance — *becomes the game*. The lantern converts far-clipping into a resource decision, gives the
player a stealth verb, and hands the renderer a performance dividend exactly when the scene is
tensest. On top of that, doubled 160x100 pixels are a *benefit* to a woodblock style rather than a
tax, the 16-colour palette is historically justified rather than excused, and the "fight the Abbot
by muzzle flash" set-piece is the kind of thing that gets a game remembered. The art-effort worry is
smaller than it looks: engraved hatching is line maths, and the brief already commits to Python
asset scripts. Highest ceiling, and the risks are all mitigable with technique rather than with
scope cuts.

**2. HADAL.** The safest *good* game here. Its fog is diegetic, its palette ramp is elegant, and the
air-timer loop gives an eight-level run a spine with almost no systems cost. It ranks second only
because its central idea (limited air) is a familiar one, and eight steel decks fight sameness in a
way the palette-tint trick only partly solves. If the schedule tightens, this is the concept whose
scope compresses most gracefully — cut two decks and it is still whole.

**3. BLACK ICE.** Technically the strongest fit by a wide margin: black floor and ceiling, geometric
textures, aggressive far-clipping, cheapest art, best frame rate, and the trace meter is a genuinely
good escalation system that costs one palette animation. I rank it third purely on distinctiveness —
neon cyberspace is the most-trodden ground of the three, and an all-geometric world risks reading as
a very good tech demo. **Caveat that matters:** if the team has no dedicated pixel artist, invert this
and build BLACK ICE first — its engine is the same engine, and the other two can follow on it.

**Cross-pollination worth stealing regardless of the pick:** MISERERE's lantern (draw distance as a
resource) is portable — it is HADAL's lamp battery, and BLACK ICE's render-radius throttle. If you
build only one mechanic from this document, build that one.
