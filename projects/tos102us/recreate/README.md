# The TOS 1.02 harness — how `tools/recreate_kit` binds to a ROM

The workspace's differential harness was built for a game: a `.PRG` loaded at `0x10000` into a 1 MB
image, surrounded by a *modelled* TOS. This project's target is that TOS, so none of the model
applies — the ROM **is** the operating system. What follows is how the kit is bound here, how to
write a case, and how to get the Tier 3 denominator for a function.

The mode itself is documented kit-side: `tools/recreate_kit/README.md` ("ROM mode") and
`TRAP_MODEL.md` ("ROM mode — the model that is switched OFF"). This file is the project's half.

## The image in ROM mode

| region | what is there |
| --- | --- |
| `$000000..$0fffff` | the **post-boot RAM snapshot** — 1 MB of a real machine, `build/boot_ram.bin` |
| `$ff0000..$ffffff` | the I/O page: decoded by the oracle's memory callbacks, never served from the image |
| `$fc0000..$feffff` | the **ROM**, mapped at its own base and **read-only** — a store is dropped and counted |
| everything else | zero, and off-image: a read answers 0, a write is dropped |

`image_size = 0x1000000` — the whole 24-bit address space, as a 16 MB `bytearray`. The whole of it
except the oracle's stack band is compared byte for byte on every case, the ROM included.

There is no `prg`, no `load_base` and no relocation: a ROM is linked for the address it answers at,
so the addresses in `include/addrs.h` are simultaneously machine addresses, Ghidra addresses and
image offsets.

**The TOS trap model is not installed.** A `trap #13` inside a ROM function is taken through the
image's own vector table by Musashi's exception processing, into the ROM's real handler. That also
means the kit's poked-input block, its Malloc arena and its staged-file window cannot be reached by
anything — the claim is re-tested after every RUN against the total number of traps the model served
(`emu._vet_rom_mode_is_modelless`), and the builders that stage that state (`console_key`,
`psg_regs`, `stage_files`, …) are refused outright.

`image_size` is therefore free to be the whole address space, but **os.h's `OS_IMAGE_SIZE` must
equal this machine's RAM** — it is the bound the CANDIDATE's kit sources use for every image access,
so `0x100000` here is the 1 MB machine and not a coincidence. `harness._vet_rom_memory_map` refuses
a binding where the two disagree, and checks the `stack_top` band lies inside that RAM.

**The seeded hardware model covers only the addresses Phase 7 names, and a read outside them REFUSES
the case.** For a game the silent 0 an unmodelled I/O read answers was a small surface; for an
operating system it is a much larger hole, so the oracle counts such a read and
`harness._vet_rom_io_reads_are_modelled` refuses the differential by address.
`Getrez` (`$ff8260`), `Physbase` (`$ff8201`/`$ff8203`), `Setcolor` (`$ff8240`+) and everything
touching the FDC are therefore out of reach — loudly — until each address is added to the model with
the evidence for what it really answers. `TRAP_MODEL.md`'s ROM-mode section has the list, and
`test/test_boot_snapshot.py` drives the refusal on a planted `move.b $ffff8260,d0`.

## The snapshot

```
make snapshot                       # capture build/boot_ram.bin (~15 s; emulation is real time)
python tools/boot_snapshot.py --twice   # capture twice and report exactly what differs
```

`tools/boot_snapshot.py` boots the **original** ROM in headless Hatari on a fixed machine —
`--machine st --memsize 1 --monitor rgb --sound off`, a blank 720 KB floppy built by
`tools/st_build.py` in drive A: — and dumps the first megabyte of RAM.

**The stop point** is the ROM's own vertical-blank handler (`$fc06de`, the `addq.l #1,_frclock` the
`$70` vector points at) at vertical blank 901, with the desktop up and idle. One exact instruction,
at a fixed count of vertical blanks from power-on; the tool reads the PC out of Hatari's register
dump and checks it against the vector table in the snapshot itself, so a capture that stopped
elsewhere fails rather than becoming a snapshot of an arbitrary instant.

*Why not the desktop's first `evnt_multi`*, which would be the natural anchor: Hatari's breakpoint
expressions dereference memory only one level deep, so `(pc).w = $4e42 && d0 = $c8` can say "an AES
call" but not *which* AES call — the opcode is two levels down, in `control[0]`. And, decisively,
once the desktop is up and nothing is typed it **blocks inside `evnt_multi` and makes no further AES
calls at all**: a breakpoint armed after any settling period never fires (measured — a 90-second idle
run of exactly that shape timed out at the desktop). The first `evnt_multi` is an instant *during*
start-up, not after it.

Hatari prints no warnings about this ROM; `log_faults()` is checked on every capture and the boot is
clean.

### What two captures disagree about — the MASK

Measured over three independent boots: **1,929 bytes of 1,048,576 (0.18%)**, and *not* the clocks.
`_hz_200`, `_vbclock` and `_frclock` are bit-identical — the stop is at a fixed vertical-blank count
and Hatari's timing is cycle-driven — and so are the whole screen, the 256-entry vector table, every
system variable, the GEMDOS buffers and the desktop's data.

What moves is the **phase of the AES's and the desktop's idle work** at the instant the vertical
blank interrupts it: the three boots stopped with different `D0/D7/A0/A6/A7`, and what differed was
the dead stack below each stack pointer plus the scratch those routines churn.

| region | what it is |
| --- | --- |
| `$0009ff` +5 | OS scratch below the Line-A variables |
| `$001464` +0x1ce | OS BSS scratch / a dead stack frame |
| `$0074c0` +0x54 | OS BSS scratch |
| `$008930` +0x2d0 | the supervisor stack, below ISP |
| `$009488`, `$009fa5`, `$00a19b`, `$00a771` | AES scratch (0xc4 / 0xcf / 0x79 / 0x6d bytes) |
| `$00c7e1` +7 | the AES process structure A5 points at |
| `$0f7fa2` +0x12 | the desktop's stack, below `_memtop` |

`MASK` in `tools/boot_snapshot.py` is the union over the three pairwise comparisons, coalesced across
gaps of 0x100 bytes — deliberately wider than any one pair's difference.

**No case may depend on a byte in there**, and that is a surface rather than a rule:
`test/test_boot_snapshot.py::test_no_verified_function_depends_on_a_byte_the_capture_does_not_reproduce`
fills every masked region with pseudo-random bytes and re-runs every verified function's
differential. **A function added to this project must be added to that case.**

## Writing a case

```python
from harness import addrs, differential, report

def _glue(lib, buf):
    return lib.xbios_random(buf)

diffs, info = differential(addrs.XBIOS_RANDOM, {"a5": 0, "_pokes": pokes}, _glue, poison=True)
assert not diffs, report(diffs)
assert info["ret"] == info["regs"]["d0"]
```

* **Addresses come from `include/addrs.h`**, through `tools/addrs.py`, which parses it. The C cores
  include the header and the cases read the same `#define`s, so an address cannot be right in the
  reconstruction and wrong in the case that proves it.
* **Enter a function the way the dispatcher does.** Both trap dispatchers (`$fc07fc`) pop the
  function number and `suba.l a5,a5`, so every BIOS/XBIOS routine runs with **A5 = 0** and reaches
  low RAM and the I/O page through 16-bit displacements off it. Pass `{"a5": 0}`.
* **Stack arguments** go at `emu.STACK_TOP + 4` (the sentinel return address occupies `+0`), poked
  through `_pokes`. That is inside the band the diff drops, which is where a caller's frame belongs.
* **Perturbing the snapshot** is an ordinary poke: `{addrs.RANDOM_SEED: seed.to_bytes(4, "big")}`
  proves a function over *inputs* rather than over the one machine that was captured.
* **Declaring hardware reads** is unchanged from a game project. A byte read of a modelled address
  (`emu.HW_ADDRS`) that nothing declared **refuses the case**; a PSG register read back without a
  `psg_seed` does the same. Pass `hw_seed={0xfffa01: 0xb0}` / `psg_seed={7: 0x3f}` — see
  `TRAP_MODEL.md`, Phases 6 and 7.
* **Off-image effects are compared automatically**: the PSG access ledger and register file, the
  hardware read and write ledgers, the scheduled-write wait counts.

## Verified functions, and their Tier 3 denominators

The oracle reports `ninsns` and `cycles` for every run (`out_regs`), so the ORIGINAL's cost per
function is a measurement rather than an estimate — that is the denominator the `recreate / original`
ratio in `STATUS.md` is divided by. `ninsns` counts one more than the instructions executed (the
reset iteration; `shim.c`'s run loop says why), and is reported here as the oracle reports it.

| function | address | case | insns | cycles |
| --- | --- | --- | --- | --- |
| XBIOS `Random` ($11) | `$fc1510` | seeding branch (state 0, as the snapshot has it) | 44 | **810** |
| | | advance branch (state `$12345678`) | 39 | **710** |
| XBIOS `Giaccess` ($1c) | `$fc2ea4` | read a register | 17 | **260** |
| | | write, then read it back | 18 | **270** |

To measure one:

```python
_, _, regs = emu.run(harness.make_image(pokes), addrs.XBIOS_RANDOM, {"a5": 0})
regs["cycles"], regs["ninsns"]
```

The numerator — the same function compiled with `m68k-elf-gcc` and run under the same oracle — comes
from `recreate_kit/asm_twin.py`'s bench path (`emu.run_bench`), which this project has not yet wired
up: **no Tier 3 ratio has been measured yet.** The denominators above are the first half of it.

## Layout

```
recreate/
├── project.toml        the ROM binding: rom / rom_base / snapshot / stack_top / image_size
├── Makefile            the kit's three lines, plus the snapshot rule
├── include/addrs.h     every ROM and system address this project names — the source of truth
├── src/<component>/    the reconstruction, one directory per ROM component
├── test/               the differentials; `harness.py` is the kit shim plus `addrs`
├── tools/              boot_snapshot.py (the snapshot), addrs.py (addrs.h as Python)
└── build/              gitignored: the candidate .so and the RAM snapshot (the ROM's own data)
```
