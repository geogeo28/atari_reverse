# The TOS 1.02 harness — how `tools/recreate_kit` binds to a ROM

The workspace's differential harness was built for a game: a `.PRG` loaded at `0x10000` into a 1 MB
image, surrounded by a *modelled* TOS. This project's target is that TOS, so none of the model
applies — the ROM **is** the operating system. What follows is how the kit is bound here, how to
write a case, and how a function gets its Tier 3 ratio.

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

**An I/O byte no model serves REFUSES the case, and the remedy is a declaration the case writes
itself.** For a game the silent 0 an unmodelled I/O read answers was a small surface; for an
operating system it is a much larger hole, so the oracle counts such a read and
`harness._vet_rom_io_reads_are_modelled` refuses the differential by address. The declaration that
answers it is `io_seed={0xff8260: 0x02}` — the DECLARED I/O MAP (`TRAP_MODEL.md`, Phase 15), which
takes any byte of the page and routes the named models' own addresses to them — so `Getrez`
(`$ff8260`), `Physbase`
(`$ff8201`/`$ff8203`) and `Setcolor` (`$ff8240`+) are reachable by SAYING WHAT THE MACHINE HELD,
which is a claim in the case rather than a change to the kit.

**A register a routine WRITES and then READS BACK is declared `write_through`**, which is the same
kind of claim one step further: the case says the register latches what is stored and reads it back
unchanged, and both cores then serve the byte the run itself wrote. It is what makes `Mfpint` (whose
enable half re-reads the IERA and IMRA its disable half cleared a bit of), the MFP timer programmer
(`$fc260e`, which writes the reload byte and re-reads it until the 68901 agrees) and `Rsconf`'s baud
arm ordinary differentials rather than slices and halts. `test/mfp.py` carries the claim register by
register — including the two pairs where it holds only because every store these routines make is a
pure clear (`TRAP_MODEL.md`, Phase 15, "The honest limit of a write-through byte").

**A register whose two successive reads must DIFFER is declared as a LIST**, one byte per read —
`io_seed={0xfffa01: [0x00, 0xff]}`, the DECLARED SEQUENCE (`TRAP_MODEL.md`, Phase 16). That is what
makes the ACIA handler's TWO-PASS entry a case at all: its loop asks the MFP after every pass whether
either 6850 still wants service, and no constant can say "asserted, then idle". A read PAST THE END
of a list is refused on both shores rather than served the last byte again.

What stays out of reach is the TRANSACTION: a register whose next answer depends on something the run
itself did — an FDC command written to `$ff8606` deciding what the next read of `$ff8604` means.
`test/test_boot_snapshot.py` drives both halves of the declared/undeclared pair
on a planted `move.b $ffff8260,d0`, and `test/test_xbios_getrez.py` is the first real function held
to it.

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
* **Declare every hardware byte with `io_seed`.** `io_seed={addrs.SHIFTER_RESOLUTION: 0x02}` is the
  one door, and it is the one most BIOS/XBIOS routines need — the shifter, the video base, the
  palette, the MFP's interrupt registers. A byte read of an I/O address nothing declared **refuses
  the case**. The declared byte is served on every read of it, a wide read is N declared bytes and
  one ledger entry, and the whole ordered stream is compared, so a read whose result the routine
  DISCARDS (clearing a status flag by reading it) is still a compared fact. The reconstruction reads
  through `hw.h`'s `io_read8`/`io_read16`/`io_read32`, which the on-target build in
  `atari/shim_include/hw.h` supplies as the real volatile access.
  * **The models are two; the door is one.** A Phase-7 named slot (`emu.HW_ADDRS` — `$fffa01`,
    `$fffc00`, …) written into `io_seed` is ROUTED into that model, which keeps its own rules and
    its own ledger; `hw_seed={0xfffa01: 0xb0}` still works and is the same declaration. Declaring
    one address through both doors is a `ValueError`. See `TRAP_MODEL.md`, Phases 7 and 15.
  * **The YM2149 is the exception**, because Phase 6's file is keyed by REGISTER NUMBER and a read
    of `$ff8800` answers whatever was last latched there: `psg_seed={7: 0x3f}`, refused by name if
    written as an address.
  * **A byte the run itself STORES to and then reads back is refused**, and no bigger declaration
    fixes it: the declaration describes the machine on ENTRY. Run the case up to the write, or enter
    past it declaring what the write left. (Where the register really LATCHES the store, say so with
    `emu.write_through(byte)` — see above.)
  * **A routine whose successive reads of one address must DIFFER takes a LIST**:
    `io_seed={addrs.MFP_GPIP: [asserted, idle]}`. The Nth read is served the Nth byte, the list works
    on a named slot as readily as on any other address, and reading past its end is a refusal rather
    than a sticky last byte — so a list is also the case's statement of HOW MANY reads it describes.
    `test/test_bios_ikbd.py`'s two-pass case is the worked example.
* **Off-image effects are compared automatically**: the PSG access ledger and register file, the
  hardware read and write ledgers, the scheduled-write wait counts.
* **A difference by nature is dropped by name, per byte**: `case.run(dropped=((lo, hi, why),))`, and every
  dropped byte must be one the ORIGINAL wrote (`rom_bench.vet_dropped`, the rule Tier 3's drops share). Where
  the run decides the extent (a stack with `link` holes, a record armed on one path), use
  `case.run(dropped_windows=...)`: only the bytes of the window the original stores are dropped.
* **An address a routine FORMS is on the 24-bit bus.** The 68000 drives 24 address lines, so a sum past
  16 MB lands where the ROM wraps it — and the host, whose image is a flat array, must wrap it the same way
  before it bounds anything (`include/m68k_idioms.h`'s `bus_dereference`: the identity on target, a mask on
  the host). Two layer policies hold that: the BIOS console forms every screen address through `vt52.h`'s
  `console_screen_block(image, at, bytes)` — form, wrap, THEN bound the wrapped span — for the cursor, the
  glyph, the clear and both scrolls (a cell past 16 MB is the row above the screen, as on the machine); and
  `vdi.h`'s call and workstation accessors (`intin_word`, `ptsin_word`, `contrl_word`, `answer_intout`,
  `work_word`, … and `caller_word` for a held cursor) SUM THE FIELD OFFSET, THEN MASK — the 68000's
  `d16(An)` — never mask the base and add. New code that dereferences a caller's pointer goes through them;
  a raw `image + linea_pointer(...)` is the parked host-SIGBUS class (`STATUS.md`). The AES reaches EVERY caller's
  pointer through one family, `m68k_idioms.h`'s `bus_span(address, bytes)` and the `bus_byte`/`bus_word`/`bus_long`
  readers with their `set_bus_*` setters (sum, wrap, access — the plain access on target). Off target it REFUSES BY
  NAME what the 68000 could not do: a word or longword at an ODD address (the address error, vector 3 — the oracle's
  Musashi is built without address errors, so no differential could show it) and an access whose bytes run PAST THE
  TOP of the bus (the host image ends there; the bound is written `at <= OS_BUS_ADDR_MASK - (bytes - 1)` so it cannot
  wrap). One spelling, so a bound is fixed once — it replaced a dozen re-spellings under nine names.
* **Stage EVEN pointers in-process.** A refusal is `recreate_not_reconstructed`, an `abort()`: an odd word pointer (or a
  span over the bus top) handed to an AES core inside pytest ends the WORKER, not the case. A case that means to show
  the refusal runs the core in a CHILD process through `vdi_helpers.refusal()` / `refusal_over()` and asserts on its
  stderr (`test_aes_resource.py`'s bus-top cases are the pattern).

## A STAGED RAM DISK — the shape the file system needed

Every case above proves a routine over the captured machine's own RAM. The GEMDOS file system
cannot be proved that way: its whole subject is a medium, and the machine this snapshot came from
has a blank floppy in drive A: that no case may spin.

**What makes a disk stageable is where GEMDOS stops.** It makes no hardware access at all, and
reaches a disk through exactly three BIOS calls — `Rwabs`, `Getbpb`, `Mediach` — which are the
dispatch table's INDIRECT entries: entries 4, 7 and 9 of `$fc0846` have bit 31 set, and the
dispatcher's `movea.l (a0),a0` turns each into a jump through a RAM VECTOR (`hdv_rw` `$476`,
`hdv_bpb` `$472`, `hdv_mediach` `$47e`). Those three longwords are ordinary system variables, so a
case pokes them — and from that moment the ROM's own file system is running against a disk the case
built, with no hardware touched by either shore and no model of a floppy anywhere.

**It is the RAM-VECTOR PAIR one layer down** — the arrangement `test/isr.py` already makes for the
routines an interrupt handler calls, and `include/staged_call.h` for the handler's own side:

* for the ORACLE, three real 68000 stubs in the case's band, which copy sectors to and from an image
  poked into free RAM, answer a pointer to a staged BPB record, and answer the MEDIA-CHANGE LONGWORD
  the case poked — which is what makes all three arms of that protocol reachable, the ROM's own
  truncation of it to a word included. They
  are hand-built from named opcode words (`test/gemdos_fs.py`, the shape `gemdos.slice_trampoline`
  uses), assembled offline by `m68k-elf-as` to get them right, and pinned by EXECUTION: a stub
  reading `recno` or the buffer pointer from the wrong stack slot transfers the wrong sector, and
  the candidate — handed the same arguments by C — transfers the right one, so the byte diff reds;
* for the CANDIDATE, a hook the case binds to `recreate_call_disk_vector` (`include/gemdos/fs.h`),
  with the same three effects in Python over the same image bytes.

**The disk is COMPARED IMAGE, and that is the whole of why this works.** The sectors, the buffer
control blocks, their 512-byte buffers, the drive media descriptor and the staged BPB are all
ordinary RAM inside the differential's byte compare — so "the ROM wrote this sector and we did not",
"we wrote it to the wrong record", "we kept a buffer the ROM invalidated" are all ordinary red
diffs. Nothing is excluded, nothing is waived, and the harness needed no new door.

**What it costs is a fourth tenant of the free window.** `project.toml` declares three
(`stack_top`, `bench_base`, `staging_base`) and `RomBench._vet_tenancy` refuses an overlap between
them. A FAT12 floppy does not fit in the 4 KB case band, so the disk takes 44 KB at `$68000` and
says so by arithmetic instead: `test_gemdos_fs_disk.py` asserts the span is clear of all three and
that the captured snapshot leaves every byte of it zero. Growing `staging_bytes` so the kit's own
vet covers it is the tidier answer and is not an agent's edit to make.

**Inside the 4 KB case band, a battery that needs several buffers at once CLAIMS a band**, through
`test/staging.py`'s `band(offset, size, owner)` — which refuses an overlap with every band already
claimed, whoever claimed it, and answers the address. Six modules claim one and the 4 KB is now full,
so a new one takes its span out of a declared tenant instead (the 8.3 name battery's is
`gemdos_fs.NAMES_AT`, inside the RAM disk's). The registry replaced a hand-written assertion per
module against the ONE neighbour its author knew about: under that arrangement two batteries' bands
sat on top of each other with every assertion still passing.

**The disk itself is small enough to read whole in a failure message** — 512-byte sectors, two per
cluster, two sectors per FAT, two of root directory, 32 data clusters, 71 sectors in all — and both
FAT and root directory are two sectors DELIBERATELY: a region whose length is not a whole number of
clusters leaves pseudo-records inside its own cluster span that map onto the region above it, which
is legal (an OFD's length stops the ROM reaching them) and a needless trap for a case that spells a
record by hand. The root holds a subdirectory, a file inside one cluster, a file spanning three, an
empty file, a deleted entry and a volume label, and each file's body is a ramp keyed on the file, so
a read landing on the wrong cluster is a wrong BYTE rather than a plausible one.

**A case here does not poison.** `case.run`'s attribution pass pre-inverts every byte the oracle
wrote, and the oracle writes `savptr` itself on every `trap #13`; what stands in for it is staging —
every buffer starts full of `$a5` and every sector holds its own ramp, so a byte the reconstruction
did not write reads as something no arm of these routines produces. That is the
character-device group's rule (`test/gemdos_console.py`) applied one layer down.

## THE AES DOOR — Line-F calls, a machine inside the dispatcher, and what the gemstart, disp and forker ports need

GEM never calls itself by `jsr`: every AES call is a `$F000|off` word, a Line-F exception whose handler — a RAM copy
at `$cc0e` that gemstart Malloc'd — jumps through the ROM call table, and every Alcyon return a `$F001|m` word whose
handler restores the registers `m` names. The C calls by `jsr`, which leaves the same machine but for ONE word: the
handler rewrites its own `movem` mask (`$cc44`) on every masked return. `test/aes.py` is the door (the VDI's shape,
its field reader hoisted into `test/layouts.py`, its naming rule into `test/routines.py`, its row registry into
`case.Rows`): an Alcyon AES routine runs over its caller's frame DIRECTLY (the row Tier 3 prices) or THROUGH LINE-F
at a staged caller that makes the ROM's own call word (verified, unpriced), the mask word dropped by name either way
(`LINE_F_MASK_WINDOW`) — and at Tier 3 with its `undropped=` companion, the word staged at the value the run leaves.
The attribution pass RUNS on every AES case but those that opt out ONE BY ONE, each with the reason forcing it on
measured (a routine that reads back a link or a ledger pointer it stored — `LINKS_UNPOISONED` in the edit battery, the
staged-trap battery as a whole): a drop reaches the kit (`harness.differential`'s `dropped`), which leaves
it out of the plain compare before deciding to run the pass and then neither poisons nor compares it, so every other
byte keeps skipped-store detection — only the Tier 3 companion runs without it (`aes.COMPANION_UNPOISONED`: with
nothing dropped the pass would invert the mask word, which the C never writes). The other `dropped_windows` users
keep their own opt-outs for their own reasons — a poisoned pointer steers the run (`vdi_entry_linea`,
`vdi_workstation`, the GEMDOS door, the redirect) — while `test_vdi_entry` has always run poisoned while dropping
its Line-A stack window, which lies in the kit's stack band. Answer words are still staged stale, and every pointer
argument is also handed in with a top byte (`aes.BUS_TAG`) to hold its 24-bit `bus_dereference`. The snapshot is
inside disp's idle loop — `rlr` NULL, `indisp` 1 — so `aes.leaf_machine()` stages the shell's PD running over the
snapshot's guard, a lever inert for a routine that never reaches `dsptch` (one that does will stage both itself); trees
are staged by SHAPE (`aes.node`/`tree_pokes`, linked as ob_add links them) or read out of the AES's own relocated
resource (`aes.resource_tree`). A routine with two call words is entered by the one most of its callers use —
ob_offset's `$f208` (the desk's binding and three AES callers), not `$f154` (the object library's own three).

A core that calls OUT takes `run_function`'s `hook=`, built by its door's ONE builder: `aes.alcyon_object_hook` for a
routine handed in and called Alcyon-style (`staged_call.h`'s `call_alcyon_object`, everyobj's), and
`vdi_helpers.staged_gemdos_hook` for the recording `trap #1` (whose host twin bounds the ledger pointer it reads out of
the image before storing through it). A core with more than six C arguments (ob_sst, everyobj, inf_fldset) is priced
like any other: the kit enters OUR side with its stack pointer lowered by the bytes that do not fit its argument area
(`tools/recreate_kit/README.md`).

The AES's FILE calls (the shell's sh_find, the resource load) take GEMDOS two ways (`test/aes_shell.py`). Over REAL
GEMDOS on the STAGED RAM DISK: the ROM's glue traps into the ROM's GEMDOS and our C hands the same frame to the
reconstructed dispatcher, its handlers bound to the reconstructed leaves, the disk holding the ROM's own resources as
files — the GEMDOS door's three windows dropped (the trap entry's register save, GEMDOS's stack, deepened for the file
system's frames, and the termination record). And over a SCRIPTED trap: a staged handler that records every call's
function and frame and answers a script — for the answers no disk gives, and for Tier 3, where real GEMDOS's register
save would differ by nature. Its host twin is reached through the reconstructed dispatcher, which RESOLVES a file handle
before Fread/Fseek; the scripted handle is staged open for it. sh_find's routine is `staged_call.h`'s
`call_alcyon_pointer` (one pushed longword), through the register-carrying hook like `call_alcyon_object`.

The AES's GRAPHIC calls all cross ONE `trap #2`, gsx2's (`include/aes/gsx.h`'s `gsx_trap`, the bridge). On target it is
the machine's own trap: vector `$88` (GEM's selector switch), `SYSVAR_VDI_ENTRY` (the BIOS's VDI door), the ROM's VDI,
which restores D1-A6, so D0 is all a call changes. On the host both hops are CHECKED against the snapshot's — a case
that repoints either halts by name, never served by the wrong code — and the VDI's own C twin of its entry is called on
the block, its dispatcher leaving through `staged_call.h`'s bare hook, which `test/aes_gsx.py` binds per case to the
C cores of every VDI function the AES's graphics reach (`vdi_functions`): both shores run a VDI, so an AES case is a
second differential of the VDI as well, compared over the whole image, the screen included. The door's default machine
is the cursor HIDDEN the way the AES hides it (the snapshot run through the ROM's own gsx_moff and continued from);
`shown_machine` is the snapshot's own. The attribution pass is vacuous on gsx_moff's and gsx_mon's call arms (it
inverts the nest both read and write, steering the ROM onto the counter path), so their cases stage every word those
arms store to something else.

The bridge has a second, smaller half: the AES's one `$a000` (Line-A init), gsx_mfsave's, which hands it the Line-A
base to find the mouse form (`gsx.h`'s `gsx_linea_base`). On target it is the ROM's own word (`.short
M68K_LINE_A_INIT`), with A0 the answer and D0/D2/A1/A2 clobbered (the dispatcher saves D3-D7/A3-A5 round it). On the
host, vector `$28` is CHECKED against the ROM's Line-A dispatcher (`$fc9f0c`) — a moved vector halts by name — and the
VDI's own `linea_init` C twin answers A0, read by the `LINEA_INIT_*` order `vdi.h` declares (pinned to the VDI
battery's). It makes no `trap #2`, so it needs no VDI cores bound.

A machine a case starts from is DERIVED from a ROM run, never poked: `case.written_by(writes)` keeps only what the ROM's own
run wrote (the stack band out), as a delta to lay over another machine (`continued_from` builds on it) — the IBM font as the ROM's gsx_tblt caches it, the
whole screen's clip as gsx_sclip(gl_rscreen) leaves it (`test/aes_objdraw.py`). A poked cache can describe a state no path
reaches — gl_font 3 over the VDI's small face drew every label in the wrong font, and every differential over it still passed.

Three mechanisms are designed and NOT built:

- **The Line-F handler's Malloc(100) and 100-byte copy**, which a rebuilt ROM must keep so every later TPA block stays
  put (its mask word then differs forever, by nature). The copy carries ORIGINAL ROM code addresses as data — the
  handler's `movea.l #$fee900,a0` and 38 bytes of the call table's head — kept at the original's value and NEVER
  relocated, the opposite policy to the fork functions below: on a rebuilt ROM, any Line-F executed jumps through
  `$fee900` into unrelated bytes. "Nothing else about Line-F is observable" holds only while SP is in the kit's stack
  band: a case on a UDA's stack (inside THEGLO) or on the dispatcher's stack at `$8c1a` puts the exception frame and
  every Alcyon `link`/`movem` frame in COMPARED RAM, and needs a stack `dropped_windows` entry (the
  `LINEA_STACK_WINDOW` precedent).
- **A real process switch** (a checkpoint at switchto's `rte`, or a staged second process whose UDA `rte`s into a
  sentinel stub), where `indisp = 1` is only a lever. savestate's CPU state — `movem d0-a5` into the UDA, the
  frame's SR and PC, SSP and USP — is the ORACLE's registers, ROM return addresses and kit-stack pointers no host C
  produces: for a C twin that block is a by-nature drop, and only a `.S` transcription compares it byte for byte.
  savestate's `lea $8c1a,sp` moves disp's frames into compared RAM, which needs a window too. The sentinel stub is
  `jmp ($2).w` (`4EF8 0002`), which writes nothing — not `pea (2).w; rts`, which writes 4 bytes onto the
  switched-to process's stack, inside THEGLO.
- **forker's `jsr (a0)` on ROM fork-function addresses**, which needs one `staged_call.h`-family hook mapping
  `AES_ROM_<FN>` to `aes_<fn>`. Every forkq caller queues a fork function by an IMMEDIATE ROM address (pushed, or —
  ap_tplay — stored in the local its forkq call pushes), and forker's recorder and ap_trecd compare against them:
  sixteen instructions, `aes.FORK_FUNCTION_IMMEDIATES`, CODE values a C port stores as the ROM's and a rebuilt ROM as
  its own (`test_aes_door` holds them as every longword of the GEM text naming a fork function, and every forkq call
  as queueing one).

## Verified functions, and what they cost on each side

The oracle reports `ninsns` and `cycles` for every run (`out_regs`), so the ORIGINAL's cost per
function is a measurement rather than an estimate — that is the **denominator**. The **numerator** is
the same C compiled by `m68k-elf-gcc` with the shipped ROM build's own flags, staged in free RAM
inside the same snapshot and entered through `emu.run_bench` over the same case:

```
make bench          # build the cores for the 68000, measure every row, print the table
```

**The table is not restated here.** `make bench` writes it to `build/bench/tier3.txt` and prints it,
one row per verified case — function, ROM address, case, both sides' instructions and cycles, and the
ratio. A copy in this file would be a second set of numbers nobody re-derives; `STATUS.md`'s Tier 3
column is the ledger's summary of the same file, and `test/test_status.py` pins it to that file
ratio by ratio so the prose cannot drift from the measurement.

Both cost columns are as the oracle reports them, which includes the **1 instruction and 40 cycles**
Musashi's reset exception charges before either entry executes anything (`shim.c`'s run loop). The
RATIO is net of that on both sides: a constant added to a numerator and a denominator pulls the ratio
towards 1.00, which on a routine this small is 3% of pure leniency.

**What the spread says**, since the table changes and this does not. The two routines with real work
in them come out well ahead of the ROM — `Protobt` at 0.23x-0.25x and `Random` at 0.62x-0.67x —
and the reason is the 1987 toolchain rather than anything clever here: `Random` pushes two longwords
and calls Alcyon's SIGNED `lmul`, which tracks both operands' signs around three 16x16 multiplies,
where GCC's `__mulsi3` does the three and stops. The LEAF routines come out behind, and the reason is
structural: every core takes `uint8_t *image` and loads it out of the frame, where the ROM reaches
the same memory through the trap dispatcher's own `suba.l a5,a5` at no cost — on a routine whose
whole body is `move.l _drvbits,d0 / rts` that one instruction is +16 cycles and reads as 1.50x.
`bench/tier3.py`'s `PERF_ACCEPTED` records every such row with its measured cost and which lettered
mechanism it is — save the TRANSCRIBED routines' C rows, which one rule carries (below). Being
faster is not a licence and being slower is not a defect: the reconstruction is held to the ROM's
BEHAVIOUR, and the ratio is what says how a 2020s compiler prices the same algorithm.

### How a row is made, and what makes it honest

`bench/tier3.py` is the registry and `test/test_tier3.py` is the gate. **The registry is not a list
anybody typed**: its rows ARE `test/test_boot_snapshot.py`'s `VERIFIED_CASES` — this project's
register of every case a battery has verified, built from each battery's own case constructors — run
again with a cost attached, and even the C argument VALUES are decoded out of the frame the case
poked. A second hand-written list of entries, registers and pokes is exactly how a ratio comes to be
a number about a case nobody proved, and it drifts silently because both lists keep working. What
the registry adds is the one thing that list cannot carry: a `CALL` entry per ROM routine saying how
our C is called (its arguments and the width its signature returns).

The gate then holds three things: every row at or under **1.10** unless `PERF_ACCEPTED` carries it
with its measured cost and a reason (or, for a TRANSCRIBED routine's C, its `.S` rows do; for C that calls
one, its shipped measurement does); every PINNED row still measuring what it was pinned at, within
0.02; and **every verified case having a row at all** — a function reconstructed without one carries
no ratio and no second differential, and before this nothing said so.

A pin does double duty. Over the bar it is an ACCEPTANCE. Under it, it is how a cost the Tier 1
differential *cannot see* is held in place: XBIOS `Giaccess`'s interrupt bracket (`ipl.h`) is a no-op
off target — the oracle enters at IPL 7, takes no interrupts and reports no SR — so deleting it
leaves every differential green, and the 46 cycles it costs are the whole of its surface.

Each row is also a **second differential**, and that is the larger half of what it buys. The cross
build is a third build of the reconstruction — the host `.so` Tier 1 proves, the shipped ROM, and
this one — so `RomBench.measure` requires the m68k build to leave the same image, the same return
value (at the width the C signature declares), the same callee-saved registers and the same chip
traffic as the ROM did, and refuses a run that read an I/O byte no seeded model serves.
`tools/recreate_kit/README.md`, "Tier 3's numerator", has the mechanism and the measured sharpness.
**A Tier 3 drop needs `undropped=`**: `vdi.register(..., dropped=((lo, hi, why),), undropped=<differential>)`
refuses a drop without a companion Tier 1 run over the row's own pokes that drops nothing, and
`test_tier3.py` runs every companion (the table prints each drop under its row).

**It also refuses an odd word or long access.** Musashi is built with address errors off, so a 68000
address error simply completes under the oracle; the shim counts such accesses instead
(`emu.odd_accesses()`), and `RomBench.measure` reds a row whose m68k build made one — naming the
address and the PC — unless the ROM made the same number at the same addresses. That exception has exactly
one user: `vst_height`'s "chain on from 0 through the 24-bit bus", where the ROM itself makes two odd
accesses (`$20027`, PC `$fce040`) and the build faithfully makes the same two. The refusal exists
because sh_envrn's and sh_find's odd-sized `uint8_t` frames went green here while bombing on a 68000
(`docs/on-target-execution.md`, taxonomy 14; `tools/recreate_kit/TRAP_MODEL.md`, "Odd word and long
accesses — counted, not taken").

Two things a target build needs that the host build does not, both in `atari/`: `target.mk`, the one
definition of the flags **and of the include paths** (the ROM build and this one read it, so a ratio
cannot be measured under flags nobody ships, and neither can compile a core against a different set
of headers), and `shim_include/`, where the headers the kit declares "off-target only" have their
target halves — `psg.h` writes the real `$ff8800`/`$ff8802` and `hw.h` reads the real `$ff8260`,
which under the oracle are decoded into the same seeded models and the same ordered ledgers the ROM's
own `move.b` reaches, and `ipl.h` is the real `move.w sr,d0` / `ori.w #$700,sr` pair.

### What ships as the ROM's own instructions — the TRANSCRIBED table

The rule for the ROM's HAND-WRITTEN 68000 (the VDI's pixel loops, its palette pair, its register
helpers; the AES's utility layer) is: port it to C first — Tier 1 proves the C — and where the C measures
over the 1.10 bar, SHIP a byte-pinned `.S` transcription instead. `include/transcribed.h` is the one place
that says which routines, for EVERY component — one table, a block of rows per component, one row per `.S`
entry — with the entry's register contract against the GCC m68k ABI (the callee-saved registers it leaves
changed). Everything else is derived from it, and the machinery is component-neutral: `test/transcription.py`
holds the staged callers, the transcription relation's runs and rows, the pinned regions and the byte pin, the
parsed table and the m68k call graph, and a routine of any component is named by one rule (`test/routines.py`:
`AES_ROM_X` is transcribed as `aes_rom_x`, its C core `aes_x`, its `.S` rows labelled `AES x (.S)`).

* **Tier 3's mechanism (T)**: a TRANSCRIBED routine's C rows may be over the bar only while EVERY one
  of its `.S` rows is at or under it, or `own` by (T←) below — verdict `transcribed`, read off the
  measurements, with no per-row entry. Delete a `.S` row, or let one drift over the bar, and the C rows
  go red with it. A WRITTEN acceptance of a `.S` row carries no C row.
* **The build contract** (`atari/target.mk`): `TRANSCRIBED_ENTRIES`/`TRANSCRIBED_SOURCES` are what the
  ROM build links for these routines and `TRANSCRIBED_C_CORES` the C twins it must not. The Tier 3 blob
  links both, because it measures both. The sources are `src/vdi/*.S` and `src/aes/*.S` — the table's
  components' — and NOT `src/*/*.S`: the BIOS's `trap.S`/`isr.S` and GEMDOS's `trap1.S` are entries of
  another kind, with no row, and every `.globl` of a listed source must be a row.
* **The declarations** at the end of the header: each entry as a LABEL a C caller reaches through glue
  naming the row's registers as clobbers — a plain C call of one does not compile — and
  `TRANSCRIBED_CORE`, the attribute every C core is defined with (`noipa`: never inlined, cloned or
  register-allocated across, so a call of it stays a call glue can replace).

**The C that CALLS a transcribed routine — the SHIPPED CONFIGURATION (mechanism (T→)).** A VDI function
round `$a00e`, the polygon layer round `$a003`/`$a006`, `v_show_c` round the sprite: C that calls a
transcribed core reaches the `.S` on target, so its cost with the C twin inside is nobody's cost. Tier 3
measures such C on a SECOND blob, `build/bench_shipped/` (the Makefile's shipped-blob rule):

* the same sources, compiled as the ROM build will be (`-ffunction-sections`) with every transcribed core
  WEAK (`-DTRANSCRIBED_CORES_WEAK`, which `TRANSCRIBED_CORE` reads — weak in the source, because the
  assembler resolves a call inside one file against the section, out of reach of the symbol table);
* linked beside `glue.S`, GENERATED by `bench/shipped_glue.py`: one thunk per core
  `test/transcription.py`'s `C_CALLERS_OF_TRANSCRIBED_CORES` names, carrying the core's name. Its shape is
  read off the entry's declaration — a register contract (`vdi.declare_primitive`: arguments loaded from the
  C slots), an Alcyon frame (`vdi.declare_alcyon`, the AES's too: GCC's longword slots repacked into words
  and longs), or a VDI function (a `VDI_ROM_<FN>` with an `_OPCODE` sibling, entered with nothing) — and it
  saves round the `jsr` the callee-saved registers the table's row says the entry changes. An AES routine
  has `_OPCODE` siblings too; a transcribed core that declares no contract is REFUSED, never glued as a
  function entered with nothing. It is the glue the declarations describe, built and exercised.

Every row whose C REACHES a transcribed core (the m68k build's call graph, `transcription.reaching_transcribed_cores`
— `v_fillarea` reaches `$a006` through `plygn`) is measured on that blob: verdict `through` at or under the
bar and OVER above it, with no entry — the measurement is also the glue's own second differential. A `.S`
that drifts takes its callers' rows over with it (measured: a 2,000-pass delay in `linea_rom_hide_mouse`
takes `v_hide_c / the arrow removed` from 1.06 to 9.61 and `vdi_locator / requested, a key` from 1.02 to
2.09, both OVER).

**The glue's own cost — mechanism (T→G), derived.** A thunk is the one thing in the shipped configuration
no ROM routine has: the ROM's compiled caller pushed the Alcyon frame (or loaded the argument registers)
inline on its way to the `jsr`, where a GCC caller hands its longword slots to a thunk that saves the
callee-saved registers the entry changes, re-pushes them as the entry's frame and makes a second `jsr`.
Measured on `do_arrow`'s arrowhead that is 128 cycles per `smul_div` call and 216 per `filled_poly` one —
94% of the row's excess, its C bodies at parity. So every (T→) row is PROFILED as it is measured (the
oracle's cycle-per-PC tally) and the cycles spent inside the thunks' own bytes are counted — the shipped
ELF's sized symbols of the generated thunks (`bench/tier3.py`, `glue_ranges`; `shipped_glue.py` emits the
`.size`). A row over the bar as shipped whose ratio NET OF THAT GLUE is at or under it is verdict `glue`,
with no entry; the table prints the net ratio on a line under every (T→) row over the bar as shipped, and
`test/test_tier3.py` refuses a written acceptance for a row the rule carries. A row over the bar even net
of the glue is its OWN body's cost, and is accepted, if at all, by a lettered mechanism at the SHIPPED
number (`vq_key_s` and `vdi_choice`'s sampled arm: (A) and (D) through the call, 1.23 and 1.26 net); an
entry typed at the C twin's number drifts and reds.

**A `.S` that CALLS C — mechanism (T←), derived, verdict `own`.** The VDI escape (`src/vdi/escape.S`) is
hand 68000 whose word table points INTO the BIOS console's ESC bodies, which ship as C; so its `.S` reaches
C through thunks of its own (`escape_to_<body>`, sized local symbols; `include/c_call_glue.h`'s
`IMAGE_ONLY_THUNK`), and a row that does is the escape's instructions PLUS the console's C. `bench/tier3.py`'s
`CALLS_INTO_C` names such a routine, its thunk prefix, the ROM spans its `.S` transcribes and the written
acceptances that carry the C it reaches (`CONSOLE_C_ACCEPTED_BY`: five `bios_bconout` console rows, cited by
key). Every `.S` row of it is PROFILED on both sides — the kit's per-PC tally covers the ROM window too
(`emu.prof_cycles`): OURS-OWN is every blob cycle less the thunks and less the C they reach (the m68k call
graph's closure of the thunks' callees), ROM-OWN the ROM cycles inside the transcribed spans; code both sides
run from the same bytes (the ROM's v_show_c through a `jmp`, the XBIOS through a `trap`, staged stubs) is in
neither. A row over the bar is `own` iff its own ratio is at or under the bar AND every cited acceptance still
stands; an own ratio over the bar reds the row even when the row as a whole is under it (a spill cannot
hide in the shared average), and the table prints the split under each such row. `test_tier3.py` refuses a
written entry for a row the rule carries. The lenience is measured and written down: the ROM's ESC A-D and J
refuse through `beq.s` to vq_chcells' `rts`, inside the span, so five rows count 16 console cycles as the
escape's own.

**C that reaches the VDI by `trap #2` — mechanism (V), derived, verdict `net`.** On target the AES's C traps into
the snapshot's own vector exactly where the ROM's does, so both columns run GEM's selector switch, the BIOS's VDI door,
the ROM's VDI and Line-A from the same bytes — 98% of the ROM's cycles on `v_pline`'s triangle row — and a whole-run
ratio would pass an AES body twice the ROM's. Every row whose m68k C REACHES a `trap #2` (the call graph's closure onto
a function holding one) is PROFILED and priced on its OWN cycles: ours every blob cycle less the thunks' (T→G), the
ROM's the cycles in the AES text and the Line-F handler's RAM copy (the Line-F overhead IS the ROM AES's own cost) less
the selector switch, measured on a run of the original ALONE. The measurement refuses a run of ours that spent cycles
in the AES's ROM spans, or whose remainder (the OS both run) differs from the ROM's by a cycle. The table's ratio
column is the own ratio, the whole run's printed beneath. A row is `net` only while its own ratio stays at or under
the bar WITH ITS GLUE COUNTED BACK ((ours + glue) / the ROM's); one under the bar only net of the thunks is `glue`,
exactly as (T→G) labels the same lenience (`vst_height`'s large font and `gsx_moff`'s v_hide_c, pinned in
`test_tier3.py`). Over the bar on its own cycles a row is OVER unless an entry accepts it AT THE OWN NUMBER — gsx_moff's
open nest, 62 -> 76 cycles, the image pointer and `$c86a`'s address being the C's floor — or its routine's `.S`
carries it (T).

**ROM addresses used as values — what a rebuilt ROM owes them.** With the image based at 0, `image +
VDI_MAP_COL` reads the 1987 table where it lies and `mouse_init` stores 1987 code addresses into RAM vectors;
both are right against this ROM and obligations on a rebuilt one. The census's scanner and its KINDS are
shared, `test/rom_data.py`'s, one census per component; `test/test_vdi_rom_data.py` enumerates every such use
in `src/vdi/` by file and KIND (a new one reds until listed): a TABLE outside the transcribed regions must
stay at its address or have every listed reference relocated; a CODE address (stored in or compared with a
vector, or handed on as a dispatcher's D0) must become the address the shipped routine is linked at; a
REGION_TABLE — inside a region a `.S` transcribes, `BLIT_EDGE_MASK_TABLE` in cpu_blit's for one — is read only
by that region's own C core, harmless exactly while the ROM build does not link it; a DISTANCE between two
addresses of one region survives relocation as it is. `test/test_aes_rom_data.py` holds `src/aes/` and
`include/aes/` to the AES's table, and also reads the other way — every instruction of the AES's ROM text
whose operand NAMES AES code (a fork function, a walker's routine, a vector start-up installs) is listed with
the routine that holds it and the band that ports it, and every pc-relative data reference of the text,
including the three that read an instruction's own immediate and the Line-F handler's write of its own movem
mask (CODE_BYTES); a new one reds.

`test/test_transcribed.py` holds the table to all of it — the make lists, every `.globl` of the
`.S` sources, the measured register sets, every core defined `TRANSCRIBED_CORE`, the list of C callers
read out of the m68k build and, in the shipped blob, each of those calls landing in its thunk — and every
transcription is pinned to the ROM byte for byte by one comparator (`transcription.assert_transcribed`)
under one spelling policy (`include/m68k_encodings.h`: an encoding GNU as would change is spelt as the ROM's
word, never excused). A battery declares each region it pins with `transcription.pinned_region(...)`, and
any test file that calls `pinned_region(` is imported to find them, whatever it imported the function as.

**An AES `.S`** goes through all of the above unchanged — a block of rows in the table, a file in
`src/aes/`, a battery pinning its region and registering its rows — under two constraints of its own:

* **Only Line-F-free hand 68000.** An Alcyon-compiled AES routine calls and returns through Line-F words
  (`$Fxxx`, THE AES DOOR above): transcribed, those would run the ROM's code through the handler's table
  from inside the blob, so it is not a byte-pinnable transcription. What qualifies is the hand-written
  utility layer (`rc_intersect` $fecd22, the optimize layer round it). A region may still carry another
  routine's Line-F words as bytes — the span from `rc_intersect` to the tails holds four — so long as no row
  entry's path executes one (`test_transcribed.py` reads the path off the oracle's profile over the row's cases).
* **The shared return tails in the SAME pinned region as their users.** The optimize layer's routines leave
  through `$fed066` (`clr.w d0; bra.s` to the `rts`) and `$fed06a` (`move.w #1,d0; rts`). Laid out in one
  region with its users (the `rts` at `$fed06e` included, so the span ends at `$fed070`), a user's `ble.w`
  to a tail is the ROM's own word and the byte pin holds it. Laid out anywhere else, every such branch
  becomes a `Relocated` displacement — the tails have no entry of their own to measure it from, and one
  into bytes no battery pins is refused by `assert_transcribed`. `test_transcribed.py` refuses a row whose
  path reaches a tail outside its region.

Measured on a scratch copy (never committed): `rc_intersect` $fecd22..$fed070 as a `src/aes/rect.S` of the
ROM's words, one table row, its core marked `TRANSCRIBED_CORE`, and a battery pinning the region and
registering its shapes through `vdi_fill`'s Alcyon frame caller — the pin, the `.globl` pin, the measured
register set (D2), ten `AES rc_intersect (.S)` rows at 1.00 and mechanism (T) over its C rows all went
through, and the `.globl` pin reddened with `src/aes/*.S` dropped from `TRANSCRIBED_SOURCES`.

**An ALCYON ENTRY `.S` is glue, not a transcription.** When AES C hands a routine BY VALUE to ROM-shaped code that calls it
the Alcyon way — ob_draw passing just_draw to everyobj (`$fea08c`) — the host case binds the ROM address to the C core, but
on target the value must be our own routine: the ROM's would run the ROM's AES code inside our build, which the (V) bench
refuses by name, and a rebuilt ROM would not hold. `src/aes/obdraw.S`'s `aes_just_draw_alcyon` repacks everyobj's 10-byte Alcyon
frame into the GCC call (the image base, then each word sign-extended into its slot) and enters the C core. It has no ROM
bytes and no row of `include/transcribed.h`: `atari/target.mk` lists it as ALCYON_ENTRY_SOURCES, filtered out of
TRANSCRIBED_SOURCES so the transcription `.globl` pin stays exact; Tier 3 counts its cycles as glue (`bench/tier3.py`'s
ALCYON_ENTRIES, T→G, like a generated thunk); and `test_transcribed.py` pins its `.globl`s to exactly that list, outside the
table. No host surface sees it, so its mutants are judged by Tier 3's second differential.

## Mutation sweeps — how a mutant is counted

A reconstruction's differential is only as good as the mutants it kills, so every wave sweeps its own C
and `.S` (the repository's `docs/agent-playbook.md` §10 has the rebuild traps). The recipe, and the one counting rule:

* **A PRIVATE build per mutant.** The mutated source is compiled into a candidate `.so` (or blob) of its
  own and the suite is pointed at it; the shared `build/` is never mutated, so a concurrent `make test`
  never measures a mutant and a crashed sweep leaves nothing to restore. Byte-check the tree after.
* **KILLED means pytest exited 1 AND its summary reports at least one FAILED test.** Nothing else is a
  kill: exit 0 is SURVIVED; exit 1 with only setup errors, exit 2 (interrupted), 3 (internal error), 4
  (usage), 5 (nothing collected), a SIGNAL (a stray `pkill`'s SIGTERM, a segfault of the `.so`) and a
  TIMEOUT (a mutant that spins) are ABNORMAL — re-run, and reported as ABNORMAL if they stay so. A sweep
  that counted any non-zero exit as a kill has credited signals and timeouts to the suite.
* **A CRASHED TEST IS ABNORMAL, NEVER KILLED — and under xdist it looks like a kill.** Every suite runs under
  the kit's watchdog (`tools/recreate_kit/watchdog.py`; a sweep that drives pytest itself passes
  `-p recreate_kit.watchdog` with `reverse/tools` on `PYTHONPATH`), which ends a test that spins past its
  budget with faulthandler's `Timeout (h:mm:ss)!` dump. Serially that ends the process before any summary.
  Under xdist the controller prints `worker 'gwN' crashed while running '<test>'` — for a segfault of the
  `.so` too — and counts that test in `N failed` with exit 1, the exact shape of a kill with no assertion
  behind it. So a run is KILLED only when it FAILED MORE tests than crashed — the classifier counts the
  distinct tests named in those lines and subtracts them. Re-classifying the 1,388 tails this project's sweeps
  had saved (at the AES foundation) under this rule moves two verdicts, KILLED → ABNORMAL, both a mutant whose only "failure" was a segfaulted
  worker (`rc_intersect`'s and `object_field`'s clip without the bus mask); every other recorded verdict
  stands.
* **Save every run's tail** beside its verdict, so the totals can be audited after the fact; report
  KILLED / SURVIVED / ABNORMAL separately, and every survivor named as equivalent, unreachable (say why)
  or killed by a new case.
* **Never `pkill` by a pattern** another agent's sweep also matches — kill the PIDs you started.

## Layout

```
recreate/
├── project.toml        the ROM binding: rom / rom_base / snapshot / image_size, plus the THREE
│                       tenants of the machine's free window — stack_top (the run's stack),
│                       bench_base (Tier 3's cross-compiled blob) and staging_base/staging_bytes
│                       (the band a case stages buffers and stub routines in). One file, so
│                       `RomBench` can refuse an overlap between them
├── Makefile            the kit's lines, the snapshot rule, and Tier 3's BENCH_CFLAGS + table
├── include/addrs.h     every ROM and system address this project names — the source of truth
├── include/<component>/ a component's own headers (bios/, xbios/, gemdos/); the shared ones stay
│                       at the top of include/, and every #include is written from include/
├── src/<component>/    the reconstruction, one directory per ROM component
├── atari/              what SHIPS: target.mk (the flags and include paths EVERY 68000 build uses),
│                       shim_include/ (the target halves of the kit's off-target headers), the
│                       rebuilt ROM image and the two measurement programs
├── bench/              tier3.py: Tier 3's registry, its bar, its pins, and the table `make bench`
│                       writes to build/bench/tier3.txt; shipped_glue.py: the shipped blob's thunks
├── test/               the differentials; `harness.py` is the kit shim plus `addrs`
├── tools/              boot_snapshot.py (the snapshot), addrs.py (addrs.h as Python)
└── build/              gitignored: the candidate .so, the RAM snapshot (the ROM's own data),
                        bench/ — the cross-compiled blob and the Tier 3 table — and bench_shipped/,
                        the shipped configuration's blob and its generated glue
```
