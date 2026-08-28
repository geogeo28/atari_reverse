# Reconstruction status — Zynaps

Human-readable C reconstruction of Zynaps (Hewson, 1988), each function **verified byte-for-byte
against the original 68000 code** by the shared differential harness (`tools/recreate_kit`: a
Musashi oracle running the real code vs. the compiled reconstruction, on the same memory image).
`../names.txt` is the source of truth for every name; it names all 188 functions, of which these
are the ported ones.

**Verified: the sum of the per-section counts below**, out of 188. Each `## Verified — <subsystem>`
heading carries its own count, so the only number an agent touches is its own section's;
`test/test_status.py` fails if a count and its rows disagree, and if a section names a subsystem
with no `src/<name>.c`.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table, and the conventions all live there rather than being restated here.

Where an argument is load-bearing it has ONE home, cited from the others:

| the argument | its home |
|---|---|
| why `tos_malloc_unused` is safe (the byte scan) | [`project.toml`](project.toml), re-tested by `test/test_heap_guard.py` |
| where each shipped preshift width comes from | `src/sprite.c`, "SHIPPED WIDTHS" |
| why the fuzz caps the frame width | `test/test_sprite.py`, `FUZZ_MAX_FRAME_BYTES` |
| what the entity record's fields are, and which are held by a test | `include/entity.h` |
| how the differential method works | [`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) |

## Verified — entity (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13c9e` | `entity_kill_if_offscreen` | 54 | ✅ verified | all 36 combinations of the four box bounds one step either side; the dead-record early return; extreme coordinates at both ends of the word; six flag words through both the clearing and the non-clearing arm, which pins `clr.b` against `clr.w`; 600-case sharded fuzz clustered on the boundaries; poison on the clearing arm. THREE RESIDUALS, all proved unobservable rather than untested — the `tst.w`-vs-`tst.b` guard, the early return, and the coordinates' signedness; see the ledger below |

## Verified — rng (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13bf8` | `rand16` | 46 | ✅ verified | the state the binary ships with (0x83e4f2b3, pinned against the image's own bytes, not against a second draw — 65,536 states share any 16-bit output), the LFSR's 0 fixed point, both all-ones/one-bit extremes, the tap mask itself, an 8-draw chain checked against an independently written Python Galois step (so oracle and candidate could not agree on a wrong step count), 400-case sharded fuzz; D0 compared against the oracle's own D0 on every case; poison on 4 seeds |

## Verified — sound (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x16b32` | `sound_lookup_tune` | 28 | ✅ verified | all 256 sound numbers, sharded four ways, which is what pins `adda.w`'s SIGN EXTENSION: 52 of the words a number can reach have bit 15 set (the first at 45, 0x80c8 → 0xf2b0, below the load base), so dropping `sign_ext16` fails at 45. Also hi-garbage and a set high byte in D1 (only `andi.w #$ff` matters, and D1's high word must come back untouched); poison on 4, including the boot tune 0x0b and the first negative offset. The routine writes NO memory, so its answers reach the diff through a `jsr`+store stub (`test/abi.py`) |

## Verified — sprite (3)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13bde` | `ship_sprite_deinterleave` | 26 | ✅ verified | disjoint, in-place (`A0 == A1`, which the seventh call site at 0x10132 does) and seven overlap offsets at row and word granularity — the read/store ORDERING is held by the overlap cases and by nothing else (measured: reversing the two half-row copies passes the in-place case and fails at +2/+10/+200/-1600); poison on the disjoint and the in-place shapes. Every byte of both destination frames is seeded with noise, so a candidate writing too few rows differs |
| `0x153f6` | `sprite_preshift8_2px` | 42 | ✅ verified | all six shipped widths (0x1e/0x50/0x5a/0x6e/0xa0/0xc8 — 0x1e and 0x6e reach it only through the tail `bsr` at 0x153e6 inside `sprite_bank_build_preshift8`) in place, six widths disjoint down to the 2-byte minimum, `frame_bytes` 0 for the `dbf` wrap (65536 rows, in-image because the slot step is then 0), four source/destination overlaps that put the source inside a written slot — which is what holds the read/store ORDER, measured — hi-garbage in D2's high half, 240-case sharded fuzz shared with the 4-px twin; the end pointer compared against the oracle's A1 on every case; poison in place and disjoint. The whole 8-slot bank is seeded, so a candidate writing an extra slot differs |
| `0x15420` | `sprite_preshift4_4px` | 46 | ✅ verified | same battery as the 2-px entry above. Seeding the slots it does NOT write (1, 3, 5, 7) is what makes the case a test at all — left as zeroes, a candidate that wrote all seven would pass |

## Suite-wide checks (not functions, so not counted above)

| file | what it holds |
|---|---|
| `test/test_constants.py` | the CLAUDE.md §5 pin, as a COLLECTOR rather than a registry so concurrent agents never edit it: every constant a battery restates equals the `#define` that owns it, every entry address equals the original's own first ten bytes, every battery declares both, no constant is defined in two files, no address has two `A_*` names, and `test/abi.py`'s scratch map clears the program, the game's hard-coded framebuffers and the staged-file table |
| `test/test_status.py` | this ledger's per-section counts against its rows, and its section names against `src/*.c` |
| `test/test_heap_guard.py` | the run-time half of the `tos_malloc_unused` waiver — ported from Joust, the other project the kit's guard is armed for. Until it landed the waiver was declared but never exercised here, because every case in the suite runs a pure leaf that traps not at all |

## Mutation check

Nineteen mutations, each rebuilt with `rm -f build/*.so` first (make's ~1 s mtime granularity has
re-run an unmutated oracle in this workspace before) — **13 killed, 6 survivors**. Re-measured in
full after the per-subsystem restructure, not carried over: the first attempt reported all nineteen
"killed" because `test_status.py` was red for an unrelated reason, which is the same lie a stale
`.so` tells. A sweep is only evidence from a green baseline.

| mutation | result |
|---|---|
| `RNG_TAP_MASK` bit 0 cleared | killed |
| `RNG_STEP_BITS` 16 -> 15 | killed |
| `SHIP_SPRITE_GAP` 1600 -> 1608 | killed |
| `PRESHIFT_4PX_PHASE` 4 -> 2 | killed |
| `PRESHIFT_2PX_SPAN` 1 -> 2 | killed |
| `SPRITE_PRESHIFT_SLOTS` 8 -> 7 | killed |
| `ENTITY_KEEP_X_MIN` 0x30 -> 0x2f | killed |
| `x > ENTITY_KEEP_X_MIN` -> `>=` | killed |
| entity alive byte cleared as a WORD | killed |
| tune table read big-endian | killed |
| `sign_ext16` dropped from `sound_lookup_tune` | killed |
| `loop_passes` dropped from the preshift row count | killed |
| preshift source read taken out of step order | killed |
| entity coordinates read UNSIGNED | **SURVIVED** |
| entity guard TESTED as a byte not a word | **SURVIVED** |
| entity early return deleted | **SURVIVED** |
| `word_sub` drops the high half (kit `machine.h`) | **SURVIVED** |
| `sign_ext16` dropped from the preshift slot step | **SURVIVED** |
| `rotate_right16`'s mask + zero guard deleted (kit `machine.h`) | **SURVIVED** |

Two of these were survivors in the previous revision and are now killed, which is the point of
re-running rather than re-quoting. The preshift read-order mutant died because the battery gained
four overlap cases (below); the `sign_ext16` one died because a glue change had quietly made
`sound_lookup_tune` unreachable from any test — the sweep is what found that, not review.

The six survivors fall into three groups, and all six are **honestly unpinned** rather than
oversights. None can be reached by seeding real data, so per CLAUDE.md they are recorded here rather
than papered over with a fabricated case.

**(a) three arms of `entity_kill_if_offscreen` that are unobservable BY CONSTRUCTION.** The routine
has exactly one store, `clr.b 14(a2)`, and that is what limits what any memory differential can see.

* *The guard's width.* `tst.w 14(a2)` spans `ENTITY_ALIVE` and the blitter's `ENTITY_PIXEL_HIT`
  next to it, but the clear writes the first byte alone. `tst.b` and `tst.w` differ only when the
  alive byte is already 0, and on exactly those records the surviving path clears a byte that is
  already `0x00`.
* *The early return.* Same argument one step further: falling through it reaches the same no-op
  clear.
* *The coordinates' signedness.* The keep band (x 0x31..0x17f, y 0x11..0xaf) lies entirely in the
  positive half of the word, so signed and unsigned readings agree on every input — a value under
  0x8000 is its own unsigned reading, and one at or above 0x8000 reads as negative (under the
  minimum) or as huge (over the maximum), and both answers are "kill". `test_extreme_coordinates`
  used to claim it held this; it does not, and now says so.

The `clr.b`-versus-`clr.w` half of the width question IS pinned — that mutation is killed above.

**(b) two arms whose input walks off the image** — `word_sub`'s high half and `sign_ext16`'s
negative slot step. `word_sub` models `sub.w` on a longword register, which differs from a plain
multiply only once the low word borrows: for the step-back that needs `frame_bytes >= 0x2000`, and
at that width the loop runs 0x1000 rows while the cursor drifts 0xfffe bytes *backwards* per row, so
the run leaves the 1 MiB image within sixteen rows. `sign_ext16`'s slot step turns negative only at
`frame_bytes >= 0x8000` (0x4000 for the 4-px entry, whose step is `frame_bytes << 1`), which escapes
even faster. The oracle bounds such an access and drops it; a reconstruction indexing `image + addr`
does not — which is exactly the class `make guarded` exists to find, and why `test_sprite.py`'s
`FUZZ_MAX_FRAME_BYTES` cap is load-bearing rather than tidiness. Every width the game ships is
0x1e..0xc8. Both stay as written because they are what the instructions do.

**(c) `rotate_right16`'s totality** — its count mask and zero guard are reached by no input: both
call sites pass a literal (2 or 4). They are there so the helper is total, in the same spirit as the
kit's own `rotate_right32` beside it, and cost nothing.

**Why the two batteries' synthetic overlaps ARE justified**, while a fabricated entity record would
not be: both sprite routines take a bare pointer pair and the game itself aliases them — all seven
`ship_sprite_deinterleave` call sites and all sixteen preshift ones pass `A0 == A1` — so behaviour
under aliasing is something the game already relies on, and the cases explore that same dimension at
neighbouring offsets. The inputs are pointers, not invented game data. What the game's own aliasing
cannot do is observe the read/store ORDER (every preshift store lands in slots 1..7 while every read
comes from slot 0), which is why the order needed cases of its own and went unheld until it got
them.

## Not reconstructed, and why

| Addr | Name | Status |
|---|---|---|
| `0x16ac8` | `sound_start` | **NOT blocked — verifiable today, and the next sound row.** An earlier revision of this file claimed it "needs the direct-PSG surfaces"; that was wrong and is retracted. Its body (0x16ac8..0x16b30) reads: `movem.l`, `bsr` to the already-verified `sound_lookup_tune`, `cmpi.b #$fa,(a1)` with an optional channel byte, an `eori.b #1` toggle on the byte at 0x16e90, a three-way select between the voice-slot structures at 0x16eaa / 0x16edc / 0x16f0e, seven stores into the chosen one, `movem.l`, `rts`. No trap, no hardware address, and every store lands in the text segment where the image diff sees it. The YM2149 writes belong to the routines BELOW it — `lea $ffff8800.l,a1` appears at 0x16b82 and 0x16b9e, inside 0x16b4e and its neighbour, which are separate functions |
| `0x153c0` | `sprite_bank_build_preshift8` | Not blocked either: it composes 0x13858 (unported) with the already-verified `sprite_preshift8_2px`, and is the natural next sprite row |
| `0x144e8` | `load_file` | Trap-bound (GEMDOS `Fopen`/`Fread`/`Fclose`), and the model serves all three from staged files — so reconstructible, just deferred past the pure leaves per the playbook's order of attack |
| `0x13c26` | `vbl_menu` | Partly off-image and NOT a plain call. It uploads eight longs from `palette_current` (0x19f46) to `$ff8240..$ff825c`, which the diff cannot see; it also ticks `raster_phase_counter` (0x198a8) mod 2 and clears `vbl_wait_flag` (0x198a7), which it can. Two further obstacles the earlier row omitted: it ends in `bsr.w $16b94` — an unported callee that writes in-image state, so the row cannot be verified before that one is — and it returns with **`rte`**, not `rts`, because it is the VBL vector installed at `$70`. Entering it needs an interrupt frame on the stack rather than the harness's ordinary return address |
| `0x14444` | `ikbd_send_cmd` | **Blocked at the KIT level, and the earlier row prescribed the wrong fix.** The routine spins on bit 1 of the IKBD ACIA status at `$fffc00` and then writes `$fffc02`. Adding `$fffc00` to `os.h`'s `OS_HW_*` set as a VOLATILE address does NOT work: VOLATILE means one declaration describes exactly one read and a SECOND read in the same run is refused — but a spin loop's whole nature is re-reading. Nor does a STATIC declaration, whose contract is that the machine's answer never changes; a status byte that must read "not ready" and then "ready" is precisely what the Phase 7 model excludes. And the write half has no ledger at all: `hw.h` exports `hw_read8` and no `hw_write8`, so a reconstruction's `$fffc02` store would be invisible on both sides. The correct fix is a shim-level ACIA model (a status byte that becomes ready after a declared number of polls, the way `sched.c` counts polls per wait site) plus an IKBD write ledger mirroring `psg.c` — playbook §5's "model the input hardware registers so busy-waits terminate". That is kit work, not this project's, and the surface that would catch it is on-target rather than the differential |
| `0x14456` | `ikbd_acia_isr` | Same `$fffc00`/`$fffc02` gap as above, and it is an interrupt handler entered around a frame rather than a called routine |

## Suite

`make test` — **143 passed**. `make guarded` — same count, 1666
candidate runs guarded across 10 workers, no fault.
