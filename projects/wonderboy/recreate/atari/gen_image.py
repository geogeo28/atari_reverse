#!/usr/bin/env python3
"""Stage the program image for the on-target Wonder Boy build — and declare what it is NOT.

WHAT THIS EMITS is the differential harness's OWN base image, narrowed to the bytes that are not
zero: the relocated `SWB.PRG` over ``[0x3f8, 0x218d0)``, with a named set of seed words written into
it. `recreate_kit.harness.BASE_IMAGE` is built by exactly one call (``loader.load_image(PRG)``), and
this uses that call, so the bytes the PRG carries on target are the bytes every green test in
``../test/`` ran against. Nothing is transcribed.

WHY THE PROGRAM'S OWN BYTES HAVE TO BE THERE AT ALL, since none of them execute here: the
reconstruction reads them. `SWB.PRG` has no data or bss segment — its 0x214d8 bytes of text carry
every table the cores index (the behaviour dispatch at $938, the sprite descriptors, the message
strings, the sound module at $17adc, the palette table), so `image + <Ghidra address>` has to hold
them at exactly those offsets. The relocation is done HERE because GEMDOS relocates a `.PRG` for the
address IT chose, which is not 0x3f8.

=======================  THE HONESTY LINE  =======================

**A STAGED IMAGE IS A DECLARED FABRICATION OF THE BOOT'S RESULT, AND THIS ONE FABRICATES ALMOST NONE
OF IT.** `game_main_loop` is `jmp`ed into with a stage already loaded; the chain that loads it — the
FDC driver, the Copylock at $ecca, `load_resource_by_index`, the tile installer at $e67e and
`sprites_cru_install` at $e87c — is UNPORTED, and two of those routines are not merely unported but
unreconstructed, so their products cannot be computed host-side at all today.

What the boot produces and this image DOES NOT CONTAIN (each a range of zeros, from the map in
`../project.toml` and the chain in `../STATUS.md`):

  $1d43e..$2103e  bg_tile_bitmaps      120 x $80 tiles the $e67e loop selects out of depacked
                                       TILEDATA.RAD. UNPORTED routine.
  $217d8..$254c0  the depacked level overlay (OVALAY<stage>.RAD), which carries bg_tile_index at
                                       $21e90 and the map. `rad_depack` IS ported and verified, so
                                       this one is computable — deliberately not taken here, because
                                       an overlay without the tile bitmaps and the sprite pool below
                                       is a stage that still cannot be drawn.
  $24898..       resource_table_header / the 20-byte sprite descriptors, and
  $25298..       the SPRITES.CRU cell data `sprites_cru_install` selects per stage. UNPORTED routine,
                                       and the resting extent is not established anywhere.
  $44000..$70000 the eight $5800 pre-shifted scroll buffers. The builders ARE ported.
  $70000/$78000  the two 32000-byte screens.

So: this image can run the routines that read the PROGRAM, and it cannot run a frame. That is the
whole boundary, and README.md's milestone table is drawn on it — M1 asserts only what a program image
plus a real machine can show.

THE OBLIGATION THIS LEAVES, recorded rather than discharged: the strongest possible reference for a
staged image is the ORIGINAL's own post-boot RAM, and it is REACHABLE — the Copylock lives inside
`SWB.PRG` rather than in the boot sector (`../../notes/bootsector.md`), disk 1's Pasti `.stx` boots
under Hatari, and `projects/joust/recreate/atari/smoke.py` already does `--parse` + `savebin 0
0x100000` against a shipped binary. A dump taken at the `jmp $4a0` that enters the frame loop would
turn every "fabricate" above into a measured byte. It is not done here and nothing in this build
pretends otherwise.

==================================================================

THE SEEDS ARE A SET, and they are the only bytes here that are not the file's. Each is a word the
BOOT would have written and the shim must not be caught reading uninitialised; each is named with
what reads it, because an unexplained seed is indistinguishable from a fudge.

Usage: gen_image.py <SWB.PRG> <out/WB.IMG>
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "tools"))       # reverse/tools — the shared recreate kit
from recreate_kit import project                         # noqa: E402
project.load(HERE.parent)                                # recreate/ — binds the kit's loader
import loader                                            # noqa: E402

sys.path.insert(0, str(HERE.parent / "test"))            # ../test/layout.py scrapes the C headers
from layout import wb                                    # noqa: E402


def word(value):
    return bytes(((value >> 8) & 0xff, value & 0xff))


# THE SEED SET. Addresses come from ../include/wonderboy.h through layout.py rather than being
# written here, so a constant that moves in the C moves here (test/layout.py is the project's
# Python<->C single source of truth).
def seeds():
    return {
        # vbl_handler's own counter. The boot chain does not write it — it ships in the .PRG — but
        # the smoke's whole M1 assertion is "this word advanced by the number of vblanks", so it is
        # seeded to a known 0 rather than to whatever the file happens to hold.
        wb("VBL_COUNTER"): word(0),

        # ...and the countdown whose expiry is the ONE arm of vbl_handler that reaches the YM2149.
        # Seeded to a small value so the M1 run witnesses floppy_deselect_drives on a real chip;
        # smoke.py reads this same number out of the map below rather than restating it.
        wb("FLOPPY_IDLE_TIMER"): word(FLOPPY_IDLE_TICKS),

        # snd_music_tick_body's ENTRY GATE ($17ca0): it returns at once while the engine is disabled
        # and no SFX flag is up. That is the state a machine that has not started a song is in, and
        # it is what makes the M1 tick deterministic — the drop-value store above the gate still
        # happens, so the two REAL hardware reads still steer, but no music driver runs over a stage
        # this image does not contain.
        wb("SND_ENGINE_ENABLED"): bytes([wb("SND_ENGINE_DISABLED")]),
        wb("SND_SFX_ACTIVE_FLAGS"): bytes(wb("SND_SFX_ACTIVE_FLAGS_LEN")),
        wb("SND_TICK_DROP_ACC"): bytes(1),
        # The byte tempo_drop_value writes from the two real hardware reads. Seeded to a value that
        # is NONE of the three it can write ($00/$2b/$48), so "the tick ran and chose" is separable
        # from "the tick never ran" — a 0 seed would be indistinguishable from the 50 Hz answer.
        wb("SND_TICK_DROP_VALUE"): bytes([TICK_DROP_UNWRITTEN]),

        # The IKBD report byte the shim's ACIA handler files into. Cleared so that "a reply arrived"
        # is a change and not a coincidence — the same clr.b the game's own boot waits do ($e494).
        wb("JOY1_STATE"): bytes(1),

        # ...and the raw scancode byte beside it, which is the one `sched_wait8` spins on. The .PRG
        # ships it as 0 already; seeding it says so, because wonderboy_main.c uses zero as its
        # "the controller has not spoken" sentinel and a sentinel that rests on an unstated property
        # of the shipped image is a sentinel waiting to be wrong.
        wb("KEY_LAST_SCANCODE"): bytes(1),
    }


# vblanks before the idle timer expires. Small enough that a short run witnesses the expiry, and
# larger than 1 so that the DECREMENT arm is exercised and not only the fire.
FLOPPY_IDLE_TICKS = 5

# Not WB_SND_TICK_DROP_50HZ ($00), _60HZ ($2b) or _MONO ($48). $ff is outside the set of three, which
# is what makes it a witness rather than a value.
TICK_DROP_UNWRITTEN = 0xff


def main():
    prg, out = sys.argv[1], sys.argv[2]
    image = loader.load_image(prg)                       # also sets loader.PROGRAM_END
    lo, hi = loader.LOAD_BASE, loader.PROGRAM_END

    for addr, data in sorted(seeds().items()):
        if not (lo <= addr and addr + len(data) <= hi):
            raise SystemExit(f"seed {addr:#x}+{len(data)} falls outside the staged block "
                             f"[{lo:#x},{hi:#x}) — the .PRG would never receive it")
        image[addr:addr + len(data)] = data

    blob = bytes(image[lo:hi])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(blob)
    print(f"{out}: {len(blob)} bytes  [{lo:#x},{hi:#x})  + {len(seeds())} seeds")


if __name__ == "__main__":
    main()
