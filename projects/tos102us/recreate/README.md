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

**Two captures are never bit-identical, so anything that HASHES across trees pins one file.** A row, a
scenario or a derived machine is a reproducible object PER SNAPSHOT: the same sources over the same
`build/boot_ram.bin` give the same bytes, and a fresh capture gives others (451 bytes between two made three
days apart). A comparison of row hashes, scenario hashes or cached derivations between two trees — a review's
"did any pre-existing row move?", a mirror built from `git archive`, which has no `build/` and so captures its
own — must first COPY one `boot_ram.bin` into both and check its `shasum` after every run. Measured the hard
way: a HEAD tree with a fresh capture showed 48 "moved" rows of 1,511; over one snapshot, 0.

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
  wrap). One spelling, so a bound is fixed once — it replaced a dozen re-spellings under nine names. The setters also
  refuse BY NAME a STORE any byte of which lies at or above the top of RAM (`ST_RAM_BYTES`, `$100000`): the oracle drops
  such a store and an ST loses it or takes a bus error, while the host C would write its image (fm_strbrk's 5th alert
  button reaches `$ff1100`). Reads are not refused; on target the store is the plain one.
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

A third way, for a routine whose SEARCH must be priced, or whose GEMDOS calls come inside an interactive session:
GEMDOS REPLAYED (`test/aes_fslib.py`). The scripted trap answers what a case wrote down; the replay answers what THE
ROM's OWN GEMDOS answered. `replay_script` runs the ROM's routine over the staged disk into real GEMDOS, watched at the
`trap #1` handler; at each call the ROM's GEMDOS is called by a real `trap #1` over the memory as it stood there, and
its D0 — and for a search the 44 DTA bytes — become one script entry. `replayed(name, path)` is the machine with that
script staged behind a `trap #1` handler that answers it call by call and RECORDS every frame in a ledger, both tables
in the image, so the differential compares them (a call made with other arguments, or one call more, reds though
nothing the caller can see changed). A test holds the replayed run to the real disk's run wherever the caller can see
GEMDOS. Both the scripted trap and the replay are one machinery, `aes_shell.Table(pointer_at, entries, stride, what)`: a
table a longword in the image points into, `staged` at a run's start, `next` bounding the pointer the host twin reads
out of the candidate's image before it stores through it, `record` and `recorded` for a ledger. The two 68000 stubs
stay their batteries' own (a new compare in a shared stub would move every priced row over it); `REPLAY_CALLS` (128)
bounds a script, so a session making more GEMDOS calls than that is refused by name.

WHY TIER 3 CANNOT PRICE OVER REAL GEMDOS: the trap entry's register save holds the CALLER's registers, which differ
between the ROM's code and GCC's by nature — a priced row may leave nothing out of its image compare without a named,
vetted drop, and GEMDOS's three windows are too wide for one. Over a staged handler both shores trap into the same few
instructions at the same PC and the glue parks the ROM's own return sites on both, so the replay needed no drop of its
own. Real GEMDOS stays a Tier 1 surface: the event-free routines run over the staged disk on both shores, a session's
replayed run is held to the ROM's real-disk run of it wherever the routine can see GEMDOS, and the arms only real GEMDOS
makes (keys typed ahead, an exhausted arena) run in process on both shores.

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
THE PRINCIPLE holds for the scheduler too: a running process, a parked one, a woken one are states the ROM's own scheduler
PRODUCES (an event delivered, disp's loop `$fe4dda` run until the woken process leaves its evnt_multi at `$fe6c5c`) — never
rlr / indisp / PD_STAT / the lists poked into place, and a case no derivation reaches within one oracle run is refused.

A STAGED APPLICATION (`test/aes_pdpipe.py`) is the ONE way the suite makes a third process, and a labelled class of
its own. What it is allowed to be: the ROM's own pstart run over a stub of EXACTLY three instructions — a push of one
immediate, ONE Line-F call of a routine `aes_pdpipe.ALLOWED_CALLS` names (each with its reason; a new one is added
there by the wave that needs it, and the WIDTH its one argument is pushed at), `jmp (SENTINEL).w`.
`staged_application(call, argument)` makes it; `vet_the_stub` holds the shape where it is made, and EVERY road that
runs the dispatcher into the stub — `started`, `called`, `at_aqueue_from_the_dispatcher`, a scenario's own watched
run (`aes_evasync`) — holds the bytes as they LIE in the machine where it is entered (`vet_the_application`: the
class's shape, the call the application names, the argument it names at that call's width; a stub poked afterwards
is refused). A QPB whose bytes would land on the stub's room — it lies directly behind the read buffer — is refused
where it is staged (`qpb_pokes`). The machine differs from its start exactly where pstart's own ledger stored.
`started` is the dispatcher's own loop entering the application; `called` is that same run carried on until
the application's one call has parked it — never a call re-entered from the harness. Where it may not be cited:
- it is TIER 1 ONLY — no row of `case.ROW_REGISTRIES` or `transcription.TRANSCRIPTIONS` may run over one
  (`test_aes_pdpipe` holds both registries);
- every case over one carries the label (`aes_pdpipe.STAGED_APPLICATION`) in its name;
- nothing learnt on one is quoted as what a REAL third process (an accessory) does — a STATUS row or a finding that
  stands on one says so.

ARGUMENT-CLASS MACHINES BY THE ROM'S OWN iasync — a sibling class, labelled like the staged application and stronger
than it. A machine no ROM caller leaves but every byte of which the ROM wrote: the ROM's own `iasync(code,
parameter)` run MORE THAN ONCE for the running process over a scheduler's machine (`aes_evlib.after_iasync` —
iasync does not block; ev_block's mwait does), and its own apret (`after_apret`). Two and three delays pending, two
waits of one process on the screen's lock, nine event bits held, two events come. Each says so in its scenario's
name ("the process queued itself (the ROM's iasync)"). Unlike a staged application's they MAY register Tier 3 rows:
no instruction the ROM does not run is staged. Reach for it before the staged application — three "unreachable"
arms of the waits (a delta list walked past two, a ninth event bit, a MOBLK over its own EVB) were each one or two
calls of the ROM's own iasync away.

THE `leaf_machine(onto=)` TRAP. `aes.leaf_machine` lays its lever OVER `onto`, not under it: AES_RLR := the shell's PD
and AES_INDISP := 1, whatever `onto` held. Never hand it an `aes_event` machine — one whose running process the
scheduler made (`aes_event.machine()`, `screen_manager_running`, a staged application's): it puts PD0 where another
process may run and sets a guard no running process has, a machine of neither kind. Such a machine is run as it is
(`aes.run_function`, the battery's own `run`).

A CASE THE ATTRIBUTION PASS STEERS SAYS WHAT STEERS IT, AND THE PASS IS NARROWED TO THAT — one spelling,
`aes.run_function(..., steered=<reason, or several>)`, used by the processes' and the lists' batteries alike. A
routine that computes a store's ADDRESS from a word it also stores (a UDA's saved stack pointer, the count getpd
indexes the PD table by, a pipe's index, a list's links) is steered by the pass's inverted word. A REASON
(`aes.steers(why, *spans)`; `aes_pdpipe.STEERS_THE_STACK` / `_PD_COUNT` / `_INDEX` / `_LISTS`, and `_QUEUE_POINTER` /
`_QPB` for the overlap cases whose run stores over what it was handed) names THE WORDS that steer, and it is held on
every run of the case: the pass is still made, with those words left as they are and every other byte the ROM's run
stored inverted — so a flag, a mask, an answer, a count the C did not store shows, and a reason that names the wrong
word, or too few, fails by name. A case names every reason its run meets, the first met first.
The other direction is a sweep run on demand: `AES_STEERED_FOR_NOTHING=1 pytest test/test_aes_pdpipe.py
test/test_aes_evasync.py` makes the pass once more per reason with THAT reason's words inverted too, and a reason the
case survives without is refused by name. Run it when a steered case is added or a routine under one changes (last:
2026-10-04, band 4 wave 0's gate fix — six labels corrected, 732 cases green under it; and 2026-10-06 over the
input's batteries, `test/test_aes_evinput.py test/test_aes_evfork.py`: 1,163 passed).
A REASON IS NAMED WHERE A WORD STEERS, NOT WHERE THE ROM STORES IT — the trap the input's first table fell into
(315 of 1,031 cases narrowed for nothing). Which reason steers which routine is MEASURED, each left out in turn
(`aes_evinput.STEERS`); a reason that steers some cases of a routine and not others (`STEERS_SOME`) is asked of each
case — the pass tried WITHOUT it first and the reason named only where that fails (`aes_event.run_core_steered`).

THE EVENT DOOR — the AES's C into the event layer and the scheduler (band 4), which C holds only as far as band 4 has
ported it (REBINDING THE DOOR, below, says how an entry leaves the door). Every C call of one of
their routines goes through ONE wrapper in `include/aes/evdoor.h`, keyed by the routine's ROM address (wave 0: ev_multi
`$fe6998` and ap_rdwr `$fe65c4`; wave 1: tak_flag `$fe4e5a`, unsync `$fe4eb8`, ev_block `$fe6874`, ct_chgown `$fe49ba`,
post_button `$fe52e2`, and ev_multi's two-rectangle shape; wave 2: ev_button `$fe68a4`, fm_button's wait for the rise —
one wrapper, one `ENTRIES` line, one census line each). On target the wrapper IS the ROM's call: inline asm pushes the
Alcyon frame once, from registers or immediates (a constant-zero argument pushes the already-zero A1), and `jsr`s the
routine, D2/A2 given up (the Line-F handler loads them on every call the routine makes) — no `.S` call-out, which measured
1.84 against the inline form's 1.04. On the host the wrapper packs the frame big-endian, CHECKS the hop the ROM caller's
Line-F word takes (vector `$2c` → the handler copy, its `movea.l #` → the call table `$fee900`), and hands it to
`recreate_call_event_door`, which `test/aes_event.py` binds per case (into the lib the calling process loaded — a child
process binds its own) to a NESTED ORACLE RUN of the routine over a copy of the candidate's image: its writes laid back,
its D0 answered, every frame it is handed compared with the frame the ROM's own run hands the same entry (MOBLKs and
buffers read through their pointers). The nested run is REFUSED by name — halting the core through
`recreate_not_reconstructed`, never answered with a fabricated 0 — when the entry is not served, when it touches the
hardware or overflows the write ledger, when it overruns its measured cap (`NESTED_RUN_INSNS`, a margin over the deepest
reachable call), and when it reaches the dispatcher (`dsptch`): that call WOULD BLOCK, and only the snapshot's indisp = 1
would turn it into "no event". One thing differs by nature: the BIOS trap's register save under the keyboard poll
(`$8de..$905`, the CALLER's registers), dropped by name in Tier 1 while priced rows move `savptr` into the stack band.
Tier 3 prices such C on its own cycles, mechanism (EV): our run is WATCHED at the door entries (the kit's
`RomBench.measure(watch=)`), each door call a window taken off the ROM's own cycles, an AES cycle of ours outside a window
refused, and the ORIGINAL's run watched too — its windows must equal ours one by one, cycles and frames. The inline-asm
wrapper and the nested run are the shape of an entry the ROM still SERVES; an entry band 4 has ported is REBOUND.

REBINDING THE DOOR. An entry with a C twin is REBOUND: its wrapper keeps its signature and its callers, and calls
`aes_<entry>(image, …)` on both builds (tak_flag, `src/aes/evsync.c`, was the first). WHICH ENTRIES ARE REBOUND TODAY
IS NEVER LISTED HERE — ask the build: `aes_event.REBOUND` (the wrappers spelt through the macro, read off the
library), `aes_event.PENDING` (a twin linked, its wrapper still the ROM's call) and `aes_event.ENTRIES` less both (the
ROM's own routine through the nested run). On target that call is the whole wrapper. Off target it is still an
ARRIVAL:
- THE HOOK'S THIRD ANSWER. The wrapper packs the Alcyon frame and asks `recreate_call_event_door` as before; for a
  rebound entry the hook answers `EVDOOR_ARRIVED` (not `EVDOOR_SERVED`): the frame is recorded for the frames-handed
  comparison and the interrupt due at that door call is laid, exactly as at a served call — then the twin runs over
  the candidate's image and its answer is reported to a second hook, `recreate_event_door_returned`. A wrapper and a
  hook that disagree halt by name, both ways (a rebound entry served by the nested run; an entry left to a twin its
  wrapper does not call).
- `REBOUND` IS DERIVED FROM THE WRAPPER'S SPELLING, never listed and never from "a twin exists". An entry is rebound
  when its `evdoor_<entry>` is spelt through `EVDOOR_REBOUND(entry, ENTRY, (parameters), packed frame,
  arguments...)` — or `EVDOOR_REBOUND_VOID` for an entry that answers nothing (`aes/evdoor.h`). That one spelling is
  the target wrapper (the twin's call), the host wrapper (frame packed → arrival → twin → return reported) and a
  MARKER in the host library (`evdoor_rebound_<entry>`, defined once in `src/aes/evdoor.c`). The macro BUILDS the
  twin's call itself, `aes_<entry>(image, arguments...)`, from the entry's name: a wrapper spelt rebound can call no
  other twin. `aes_event.rebound_in(lib)` reads the markers (a child reads its own library's), Tier 3 reads the blob
  (`tier3.rebound_entries(elf)`: a twin linked and no `jsr` into the ROM routine left), and
  `test_the_blob_s_rebound_and_pending_entries_are_the_host_s` holds the two equal on both blobs.
- A TWIN THAT MERELY EXISTS IS PENDING (`aes_event.PENDING` = `twins_in(lib)` − `REBOUND`): exported, defined with
  `EVDOOR_TWIN`, its wrapper still the ROM's call. Band 3's C keeps reaching the ROM's routine through the door (a
  window); the event layer's own C reaches the twin by its core (an arrival of nothing: no hook is asked); nothing
  is flipped. A pending twin already owes what a rebound one owes — its leaf battery's priced rows, no wrapper
  reached from it — so the day it is flipped nothing is found out.
- HOW A FLIP IS MADE — ONE EDIT. (1) The twin, `EVDOOR_TWIN aes_<entry>(uint8_t *image, <one parameter per frame
  field>)` (`include/transcribed.h`: `noipa`, so GCC neither inlines it into a same-file caller nor clones it, and its
  first instruction stays the arrival point both watches stop at), and its leaf battery, land PENDING and are
  reviewed. (2) THE FLIP is the entry's wrapper re-spelt through the macro in `aes/evdoor.h` (and the include that
  declares the twin) — nothing else by hand: `REBOUND`, the shadowed set, the census's `aes/evdoor.h` row and Tier
  3's lists of door calls follow by derivation. (3) Rehearse it first on a private mirror of the tree (host library
  and both blobs built by the tree's own rules): the whole suite, every door-arriving row measured on its own, the
  table. (4) The flip's commit carries the table before and after, every moved row old → new, and STATUS's ratios
  re-quoted from its own `make bench` (`test_status` is red until they are). (5) A flip's twin mutants are swept
  through the door batteries AND each twin's leaf battery alone; a host sweep through `amut/mutlib_plugin` switches
  the bench's second differential off, so the five `test_aes_event.py` tests OF that differential are deselected (they
  fail on the unmutated control).
- A TWIN IS CALLED, NEVER JUMPED TO. The ROM reaches an entry by a Line-F call word and gets control back. A target
  wrapper that were `return aes_x(...)` alone is, in a caller that returns the wrapper's answer (wind_update's
  `return evdoor_unsync(...)`), a tail `jmp` into the twin: the twin is entered holding its caller's CALLER's return
  address — the run's sentinel for a row entered at that caller — and the watch refuses it "not a door call". So the
  macro's call is followed by `EVDOOR_A_CALL_NOT_A_JUMP` (`include/transcribed.h`): a read of the function's own
  return address, its value dropped — no instruction, and NO WEIGHT in GCC's inline size estimate (an empty `asm`
  weighs one instruction: measured, it changed what GCC inlined in a committed object). A twin that returns another
  twin's core's answer spells the same statement after its call. Held on the blobs:
  `test_tier3.py::test_no_twin_is_jumped_to_on_either_blob` (every instruction naming a twin's first instruction is
  a `jsr`) and `::test_a_rebound_wrapper_in_return_position_is_a_call_of_its_twin`.
- THE SHADOW IS A FLIP'S RED PROOF AND BISECTING TOOL, KEYED ON HOW THE ROM ROUTINE'S RUN ENDS. Every rebound entry
  of the library a binding serves is shadowed (`aes_event.shadowed_among`; a case may narrow `SHADOWED`): each
  arrival also makes the ROM routine's nested run over a COPY of the image — to its return, or AS FAR AS DSPTCH. A
  twin that returns is held to the first (`vet_the_shadow`: the image, and the answer where the entry's
  `ENTRY_FRAMES` row says it answers — post_button and unsync answer nothing a shadow may compare); a twin that
  reaches the dispatcher's hook is held THERE to the second (`vet_the_shadow_at_dsptch`: the image at dsptch, the
  same kind of switch), before the hook refuses. A twin that ends the other way is refused by name at that end. In
  a child a shadow's refusal ends the run with its own status (`CHILD_SHADOW_REFUSED`), and `interrupted` fails by it
  whatever the ROM's run did. A wrong twin then reds at its own call, in the shadow's words, instead of at a
  session's end. One `ENTRY_FRAMES` row per entry decides its frame, its inputs' reader and its answer kind.
- A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION. A door case reaches an entry only
  in the states its caller makes, and the shadow sees the same states — it changes where a red is NAMED, never what
  is covered (measured at the pilot: five real mutants of the twin that are not equivalent pass every door battery,
  shadow on or off, and the twin's own battery kills all five). So a flip needs the twin's own battery first: its own
  priced rows, entered at the entry itself, reaching every arm, over machines the ROM's scheduler makes —
  `test_tier3.py::test_every_twin_has_a_leaf_battery_s_rows` refuses a twin LINKED without them — rebound or pending:
  the battery is owed the day the twin lands, not at its flip — and "the shadow covers it" is no coverage argument.
  A leaf battery is COMPLETE when every arm, every list shape the scheduler can make (first / middle / last / only)
  and every piece of 68000 integer semantics (a width, a sign extension, a signed against an unsigned branch, a
  re-read after a call) is killed by a mutant in the battery's own sweep, run against the battery ALONE. What the
  door cases hold is what no leaf battery can: the callers still arrive with the same frames, at the same ordinals,
  taking the same deliveries.
- A TWIN CALLS ANOTHER ENTRY'S CORE, NEVER ITS DOOR WRAPPER. `evdoor_<entry>` is for callers OUTSIDE the event layer.
  The host's hook counts every wrapper call as an arrival; the ROM's watched run and our blob's count the outermost
  door call only (on target a rebound entry's wrapper IS the core's call). A twin going through a wrapper would shift
  every later ordinal — frames compared, deliveries laid, slices marked — on the host alone. Held by the build, a
  DERIVED test: `test_aes_event.py::test_no_twin_reaches_a_door_wrapper` builds THE HOST BUILD'S OWN CALL GRAPH —
  every source compiled as kit.mk compiles it (`$(CC) $(CFLAGS)`, as make expands them), each object's functions and
  what each one's instructions refer to (its relocations), closed across files — and holds every function a twin —
  rebound OR PENDING (`aes_event.twins_in`) — reaches free of the door's two hooks: a wrapper called by a helper in
  another file is seen too.
- ...AND AT RUN TIME: while a twin runs (its arrival made, its return not reported) every hook call — an arrival, or
  a call of an entry the ROM serves — is refused by name ("called through its wrapper INSIDE the twin of …"). HOW is
  the binding's: in a CHILD the hook answers REFUSED and the core halts with those words in its stderr; IN PROCESS a
  halt would be the worker's abort and every captured word lost, so the binding KEEPS the refusal, serves the call
  as the door would, and fails the case by those words when its pass closes.
- A RUN ENTERED AT A DOOR ENTRY (a twin's own row, its leaf battery's watched cases) makes no door call of that
  entry: `DoorStops.entered_at(pc)` leaves the run's own first instruction out of the stops it starts with — the
  bench stops at a listed PC before executing it — and watches it again from the first stop on. The outermost entry
  reached inside is door call 0 on both shores. The same holds for every watched run of the ROM's: the interrupted
  derivation (an interrupt is asked for only at an ARRIVAL, `DoorStops.opens_a_call_at` — asked at the run's own
  entry, door call 0's was delivered twice), the replays (`delivering(delivered, entered_at)`), the marked runs (a
  session's slices) and Tier 3's original of an interrupted row. So a wait entered at its entry can be taken through
  an interrupt at its ev_block and priced.
- THE EVENT LAYER'S OWN C AT DSPTCH: `aes_event.switches_where_the_rom_does(name, arguments, pokes, switches=BLOCKS
  or YIELDS, dropped=…)` — the core in a fork halts at the dispatcher's hook, as a call that blocks / yields, and its
  image there is the ROM's own run's at dsptch (`rom_at_dsptch`), outside the stack band, the mask word, the trap
  save, the SR save words the ROM's run stored and the case's own named drops (each required to be bytes that run
  wrote). This is how every blocking arm of a wait is verified; nothing runs after the switch.
- THE DISPATCH HOOK REFUSES. A twin that reaches dsptch calls `aes_dsptch` (`aes/switch.h`): off target that is
  `recreate_dispatch`, asked before any guard, whose binding in every case and every child refuses by name — "the
  call would block" or "would yield", told apart by the running process's PD_STAT as disp tells them — and prints the
  frames handed so far. A run that blocks inside a rebound entry is compared where its twin stops, AT dsptch; inside a
  ROM-served one at the entry of the blocking call, as before.
- SR SAVE WORDS, AND THE LEDGER RULE. The words a bracket parks (`sr_mask_saving` / `sr_restore_from`, `aes_spl7_save`
  / `aes_spl_restore`: nothing stored off target, the ROM's two instructions on it) are each a NAMED drop out of ONE
  table, `aes_event.SR_DROPS` `{save word: why}` (psetup's `$8998`, spl7's `$8996`); `sr_drops(*words)` makes a
  case's `dropped_windows`. A WORD IS DROPPED ONLY WHERE THE ROM'S RUN STORED IT, at every place two shores are
  compared, by one rule (`aes_event.not_compared_where_the_rom_stored`: the ROM's memory as compared against what
  its run started with) — no SR byte is left out unconditionally, so no battery lists which routines reach a
  bracket, and a C that writes a save word the ROM's run left alone is red. AT TIER 3 THE DROP IS SYMMETRIC: a row
  that drops a save word is held to OUR run's ledger having stored it too (`tier3.vet_our_run_stored_its_sr_words`)
  — a build whose mask bracket was lost would otherwise hide behind the drop; it is what pins a bracket's PRESENCE
  on target, which no host battery can (the host stores no SR). The dispatcher's own (`$8994`) is stored after
  dsptch, where no host core goes. A door row that reaches a bracket THROUGH A REBOUND TWIN must name the drop
  itself (`sr_drops(...)`): the bench's second differential of an interrupted door case drops the mask word only.
- ONE LONGWORD A PARKED ap_rdwr DIFFERS IN BY NATURE — THE PARKED QPB. aqueue keeps a pipe wait's QPB by its ADDRESS
  in the EVB it queues, and ap_rdwr's QPB is its own argument frame: a place in its caller's stack on each shore
  (the twin's: a host slot per process, below). Where the wait PARKS, that EVB_PARM is dropped BY NAME and VETTED
  (`aes_event.parked_qpb_drop`): only for ap_rdwr on a pipe, only the newest EVB of the running process — the same
  EVB on both shores — and only where each shore's longword is an address in ITS stack band naming the same eight
  bytes (process, count, buffer). Used by the leaf batteries (`aes_evlib.held` vets wherever it drops), the shadow
  at dsptch, and `interrupted` where a door user blocks inside a rebound ap_rdwr. Never a window.
- A HOST SLOT PER PROCESS. A frame local that stays live while its process is BLOCKED — its routine reached the
  dispatcher with the local's address parked in a record another process reads — is live in two processes at once:
  ap_rdwr's QPB, which a parked pipe wait's EVB points into until the other end serves it through that address. In
  the ROM each is on its own process's stack. Off target such a role is `HOST_PROCESSES` frames
  (`host_slot_claim_for(ROLE, local, process)` / `host_slot_release_for`, `include/host_slot.h`), the RUNNING
  process's id choosing one: an address the IMAGE decides, the same in whichever host run laid the frame (a "next
  free slot" would collide across runs — a parked frame is laid in one run and read in another). On target the
  macro is the local's own address and `process` is not evaluated. Every OTHER slot a routine holds across a wait
  has this shape the moment two C processes can be inside one routine (wave 3's audit).
- TIER 3: THE ARRIVALS RULE. Both runs still arrive at a rebound entry — the same ordinal, delivery, slice mark and
  frame — but it opens NO window: the ROM routine's cycles stay the ROM's own, the twin's are ours, and the table's
  sub-line counts "N call(s) of a rebound entry in the own cycles". A twin that runs an AES ROM cycle is refused by
  name (rebind the entry it called first). So a flip MOVES every row that reaches the entry: save the table before
  and after, list every moved row, and hold that no other moved. A row stops being (EV) by derivation when its
  function's last `jsr` into the AES text is gone.

INTERRUPTS AT A DOOR ENTRY. A loop like mn_do or gr_dragbox only leaves its later states when the mouse or button changes
WHILE it runs. `aes_event.interrupted(name, arguments, machine, {k: effect})` delivers that change on both sides. The ROM's
watched run is stopped at the k-th door entry. The ROM's OWN interrupt code (the VDI mouse ISR and the tick glue: `press`,
`release`, `move_to`) then runs over a copy of the memory at that point, with its stack frames left out. The bytes it wrote
are laid in at that same entry. The C, in a child, gets the identical bytes at the same ordinal before its nested run.

The case compares whether the call returned or blocked, the answer, every frame handed over and the whole image. RED tests
show that dropping the delivery on either side, or shifting it by one ordinal, reds. This obeys THE PRINCIPLE because nothing
is poked: an interrupt arriving while a process is inside an event call is a reachable interleaving, and its effect is the
ROM's own ISR run over the ROM's own memory.

Tier 3 prices an interrupted row and vets it in full. The row carries its deliveries (`delivered`, the ninth
VERIFIED_CASES field, `{door call: (found, wrote)}`), laid at the same door calls at zero cycles on ALL FOUR of the row's
runs: the measure's original (`RomBench.measure(original_watch=)`) and the windows run — both watched originals, the kit's
`rom_bench.watched_original`, the bench write ledger keeping the mask word's drop vetted — our blob, and the shipped blob;
and the VERIFIED_CASES sweeps replay the row watched (`aes_event.replayed`). Each delivery is checked against the memory it
lands on. Every interrupted case whose ROM run returns, registered or not, also takes the bench's second differential
inside `aes_event.interrupted` — callee-saved registers, odd accesses, the write ledger, refusal tallies, streams and the
whole image — by the code path, so no list can fall behind the batteries.

KEYS are delivered as the mouse is. `aes_event.key(scancode)` is the BIOS keyboard handler run at the door entry
(`scancode_of` reads the snapshot's unshifted Keytbl), and `typed(...)` the next key at each ev_multi entry, all in ONE
watched run: at each delivery the run is set aside, the interrupt runs over a copy, and the run is continued AT that entry.
A routine's waits are numbered as it makes them: `aes_event.Waits({k: interrupt or (interrupt, ...)}, at=entry)` delivers at
the k-th call of `entry` whatever other door calls come between (the entry checked at every call, the count per run;
`typed` is a Waits of keys); `double_click` is three packets inside the click delay through the VDI mouse ISR, then the
ticks. Every bench entry of ROM code — watched originals, `parked`, the continued runs — declares no PSG or named-hardware
seed and enters with `emu.run`'s register file (`rom_bench.original_entered`), so nothing a previous run left reaches it.

A CASE'S OWN BUDGET, AND ITS CAP. Two runs of a door case have a default limit: the DERIVATION (a watched ROM run:
`DERIVATION_INSNS`, 1.5 M, which every derivation must fit `DERIVATION_MARGIN` = 5 times over) and the in-process
DIFFERENTIAL (`emu.run`'s own cap, `DIFFERENTIAL_INSNS`, 200,000). Neither default is raised for a long case — a short
derivation that began to spin would then run that much longer before it was refused. The case that needs more declares
it, from its measured run of N instructions, and the declaration is held both ways by name:
- `budget=B` (on `interrupted`, `refused_where_the_rom_blocks`, `register_interrupted`, `register_slices`, `run_event`,
  `stopped_at` …) is the derivation's budget AND that run's cap. It must be NEEDED (`5 N > DERIVATION_INSNS`: a run the
  default admits declares for nothing, whatever the declaration's size), FITTED (`5 N <= B`) and NOT STALE (`B <= 10 N`,
  `DERIVATION_STALE` = 2: a declaration written for a longer run than the case now makes, or by guess). A prefix a
  watch stops at an entry is held to the margin alone — it did not end, so it cannot be asked whether it needed it.
- `cap=C` (on `run_event`, and on `aes_fslib.run` / `run_replayed`) raises the in-process differential's limit only,
  under the same three rules against `DIFFERENTIAL_INSNS`: a run of 200,001..300,000 instructions needs a cap and no
  budget; past that one `budget=` serves both runs.
- THE CAP HAS ONE DOOR, `aes_event.capped_run`: every in-process differential of the event door's batteries that runs
  past the oracle's own cap is capped and vetted there, and a raw `max_insns=` handed to any of them is refused by
  name — the oracle's own spelling would otherwise cap a run that no rule holds. An original that does not return
  under its declared cap is refused as that, not as the oracle's bare overrun.
- A battery-wide cap (`aes_fslib.RUN_CAP`, `test_aes_wm_update.CASE_CAP`) is ONE declaration, `aes_event.battery_cap(
  insns, deepest=)`: held to the battery's deepest measured run by the three rules where it is declared, and every run
  under it then held to the margin (not asked whether it needed it). A battery-wide BUDGET (`aes_fslib.PREFIX_BUDGET`:
  the selector's prefixes) is held the same way — the declaration against the deepest prefix by a test, each prefix to
  the margin by `stopped_at`.
A registered row records its budget (`INTERRUPTED_ROWS[row].budget`), so the noise sweep's re-derivation and the row's
Tier 3 companion run under it.

A SESSION PRICED BY ITS SLICES. A long interactive routine — the file selector listing a directory, scrolled, clicked
and typed into — is one call no single row prices honestly: it is past the bench's cap, and one ratio over all of it
lets the bulk dilute its worst shape. `aes_event.register_slices(name, arguments, machine, interrupts, {label: (start,
stop)}, budget=)` registers one priced row per SLICE: the run between two ARRIVALS both shores make at the same PC.
- A slice's ends: `door_call(entry, nth)` (the nth call of a door entry — a wait, the screen lock);
  `trap_taken(handler, nth)` (the nth arrival at a trap's handler outside any door call — a VDI call through GEM's
  `trap #2`, a GEMDOS call at the replay's handler; `trap_handler(vector, pokes)` reads the PC); `ENTRY`; `RETURN`.
  Trap ends exist because a stretch may make no door call at all: fs_input's first comes after ~350,000 instructions.
- BOTH SHORES RUN THE WHOLE SESSION — the C cannot be entered in the middle of its routine — watched and MARKED at the
  two arrivals. The row's cost is the difference between its two marks, shore by shore (instructions, cycles, door
  windows, glue); the reset overhead comes off a slice that starts at `ENTRY` only. Every (EV) vet and the bench's
  second differential still run over the whole session.
- MEMORY IS COMPARED AT THE MARKS: our run must reach the slice's start after the same door calls as the ROM's and with
  the same memory (outside the stack band, the blob and the row's drops), and the same again at its stop — else the
  ratio would be of two different computations. Refused by name: a slice started one call late, "diverged before the
  slice's start", "diverged inside the slice", an end never reached, a slice that runs backwards, a session that
  blocks or has nothing delivered. `ENTRY` and `RETURN` carry no memory of their own (the whole run's differential).
- EACH SLICE IS UNDER `SLICE_INSNS` (200,000) on the ROM's own run of it; one over it is refused, to be cut finer.
- Measure before registering: `aes_event.rom_timeline(name, arguments, machine, delivered, traps=(handler, …),
  budget=)` lists every door call and listed trap with what the ROM had spent there; `slice_cost` prices one cut.
- A sliced session is taken through interrupts AT ITS WAITS (keys typed ahead leave no waits to cut at), and cannot be
  `psg_seed` / `schedule` / `regs` seeded.
- THE PARTITION TEST is what makes "the worst row" a claim about the whole session, since registered slices need not
  cover it. `tier3.uncovered_stretches(row, bench)` cuts each sliced session whole — at every door call and at every
  registered slice's ends — in one pair of runs, both shores' timelines held arrival for arrival and the pieces summing
  to the whole run to the cycle; `test_no_stretch_between_a_session_s_slices_is_dearer_than_its_routine_s_worst_row`
  holds every stretch no registered slice covers at or under the routine's worst registered own ratio. So a dear
  stretch must be REGISTERED (and shows in the table) or the test reds. The cut is not at every trap arrival: a trap
  arrival is matched by its ordinal and the memory there, not by a count, and a few hundred instructions between two
  traps have a ratio of their own that says nothing about the row they sit in.
- One session is derived once and shared. `aes_event.OncePerSession` is THE memo: built with the ONE computation it
  answers (over whatever its holder holds fixed — a base image, a build), it makes it for the first row asked of a
  SLICED session and answers it to the session's other rows, each of which must be over the same machine (refused by
  name) — any other row is computed every time and nothing is kept. Its holders: `tier3.Sessions(bench)` (a session's
  pair of bench runs, one build's — another build asked of it is refused), the snapshot's three sweeps, and Tier 3's
  companions. A Tier 3 row finds its session by the name its case is registered under (`Row.registered`,
  `tier3.session_of(row)`: a sliced row that names none is refused). `bench_differential(derived=)` takes what
  `interrupted` has just derived, and only that.
- A `trap_taken` ordinal is of the run's marks: a session cut at two trap handlers one of which is taken INSIDE the
  other would count that arrival differently in a run marked at both and in one marked at the inner alone. No session
  does; a run that did is refused by name where it happens (`DoorStops.stopped`).

A SESSION OF A ROUTINE THAT ALSO TRAPS (fs_input: `test/aes_fs_sessions.py`, `test_aes_fs_input*.py`). A session is a
schedule per wait — what the user does there, placed by the ROM's own ob_offset. Its machine carries GEMDOS REPLAYED
(above), the script derived from the ROM's own run of THE SAME SESSION over the staged disk; its child binds the
replay's `trap #1` door through `aes_event.declare_child_doors(name, source)`, which the event door's own binding does
not open. A session is held on four surfaces: the whole image at its END; the image at a WAIT it is cut short at (the
ROM blocks, the C is refused at the same call, and a dialog still on the screen is compared — a session's end only
sees a screen already given back); every VDI CALL in order (opcode, intin, ptsin); and WHAT THE ROUTINE HOLDS as each
VDI call is made (`aes_fslib.held_in`: its tree, its texts, its scratches, hashed into the ledger on both shores), which
is what sees a word set and put back between two waits.

The dispatcher refuses in two ways, matched by `aes_event.BLOCKS` and `YIELDS` (the dispatcher's own words). A call that
WOULD BLOCK leaves its process waiting. A call that WOULD YIELD keeps the caller ready but switches: unsync handing the lock to
a queued waiter does this. The core's generic halt line names both, so a bare "would block" substring passed a yield as a
block. `refused_where_the_rom_blocks(..., switches=)` compares the child's whole image with the ROM's at the refusing entry.

THE C RUNS FIRST IN A CHILD. A core of the event layer that goes wrong does not fail an assertion: a door user loops
where the ROM's run ends, a list routine walks a list that no longer ends or stores through a link that is no address
(the host's refusal: an abort), a wrapper and a hook disagree (a halt). In process each is a worker spinning until the
watchdog, or dead — a crash, which a strict sweep counts ABNORMAL. So the C runs in a child first, and the case FAILS
by a timeout or a non-zero exit (`aes_event._vet_returned`: one assertion, whichever child). Which child:
- A DOOR USER — a core that reaches a hook: a FRESH INTERPRETER with the door bound, once before the differential
  (`aes_event.run_guarded` / `returns_in_a_child`; `aes_event.refusal` is where a frame's values become its C
  arguments). Its hooks must be bound per child. Remembered per worker by CONTENT — routine, frame, binding and THE
  IMAGE the pokes make (`merge_pokes`: overlapping pokes laid in another order are another machine) — never by the
  machine's identity.
- A core that reaches NO hook (the list routines, the processes' and the pipes', tak_flag): a FORK of the worker AT
  THE CALL ITSELF (`aes_event.run_core_guarded`, through `aes.run_function`'s `first=`). EVERY run of the C the kit
  makes is forked first — the plain pass's and the attribution pass's, each over the very image and library state
  the kit hands that run — so the poisoned run is guarded too, and the verdict cannot depend on the test before. A
  case that MEANS to show a halt or a return in a child uses the same fork (`aes_event.core_in_a_fork`: exit code,
  stderr, the image as the core left it through a shared mapping, the answer; the library's models armed first, as
  a differential arms them). No interpreter started, no image file.
  - A FORK MAY SERVE THE TWO DRAWING HOOKS, never the event door's (`run_core_guarded(..., hook=…,
    serves=(isr.CALL_VECTOR_SYMBOL, isr.REGISTERS_HOOK_SYMBOL))`): the fork is made at the call, inside the case's
    pass, so the worker's bindings are the fork's — chkkbd, mchange and forker run so. A helper module declares its
    guarded routines (`FORK_GUARDED`: names, or `{name: serves}`), and
    `test_a_core_guarded_in_a_fork_reaches_no_hook_but_the_dispatcher_s` holds each to the hooks its fork serves.
  - A core guarded in a fork that REACHES THE DISPATCHER fails its case with the hook's own words — "would block" /
    "would yield" — in the guard's message. A core MEANT to end there is run by `switches_where_the_rom_does`.
WHICH ROAD IS NOT THE BATTERY'S WORD ALONE: in a fork EVERY hook the library has is bound to a refuser that names it
and ends the fork (`FORK_UNSERVED_HOOKS`, held to the library's own exports by `nm`) — a core that reaches one is
refused by name and told to take the other road, never passed vacuously by a `void` hook that did nothing; and the
host build's own call graph (every source compiled with kit.mk's flags, relocations per function, closed across
files) holds that the fork-guarded cores reach none on ANY path. The dispatcher's hook alone is served in a fork, as
everywhere: it refuses, a block told from a yield.
WHAT A FORK MAY DO: call the C and `_exit` — no test code, no import. Its descriptor 2 AND its Python `sys.stderr` /
`sys.stdout` are the guard's pipe (so a hook's printed words reach the failure under any capture, and nothing is
written to xdist's channel); a fork whose own Python raises reports its traceback under an exit status of its own
(`FORK_RAISED`: the harness's error, never "the C did not return"). A spin ends by `SIGALRM` after
`CORE_RETURN_SECONDS` (10) — the fork's FIRST act, which is also what bounds an ORPHAN: a fork whose worker died is
gone within those ten seconds.
WHO MAKES THE FORK — THE ZYGOTE (`test/zygote.py`, `aes_event.guard_fork`). A fork costs what its PARENT holds
resident (1.2 ms of a process of 85 MB, 13.5 ms at 650 MB, 23 ms at 1 GB), an xdist worker is a gigabyte by the
time these batteries run, and they make some 4,500 forks a run. So each process that runs tests forks a ZYGOTE as
its session starts (`test/conftest.py`: before the batteries are imported, when it holds the harness and the
candidate alone), and a guard's fork is made BY IT: the core's symbol and declared ctypes types, the values, and the
image the kit handed the run — copied into a mapping both share — go down a pipe, and the zygote makes the very fork
the worker would have made (the same alarm, the same refusers, the same two stderrs; the library armed as an
unseeded differential arms it).
- WHERE THE ZYGOTE STANDS IN, and only there (`aes_event.the_zygote_stands_in`): an UNSEEDED run (no keyword of
  `case.run`'s that arms the candidate) of a real function of the library, that serves NO hook, while the worker's
  dispatcher hook is the module's own refuser. Every other fork — one that serves a hook its case's pass bound, a
  seeded run, a test's stand-in core — is the worker's own. So is EVERY fork of a test that takes `monkeypatch`
  (`conftest.py` sidelines the zygote for it: the zygote holds the modules as the session started, and a patch on
  the fork's side would never run in its fork — measured, a patched arming that raises: exit 8 from the worker's
  fork, 0 from the zygote's). A process with no zygote (a script, a child interpreter, the bench;
  `AES_NO_ZYGOTE=1`) forks itself. Every fork test runs under BOTH makers.
- ITS IMAGE IS GUARDED ON EVERY RUN — PROT_NONE below and above, the guarded-image plugin's own distances — in `make
  test` too. Not a choice of strictness: a fork of the worker faults wherever the worker would; a fork of the zygote
  has another address space, and beside an unguarded image a wild store can land on memory mapped THERE alone, pass,
  and kill the worker (measured: a library storing 1 GB past its image passed 5 guards of 20 and crashed 9 workers;
  guarded, 20 of 20 fail by name). So a core that indexes out of its image fails its guard BY NAME in `make test`.
- ITS LIFE: one request at a time; it holds none of its parent's descriptors but its two pipe ends and stderr (an
  xdist worker's channel held open in it would hide the worker's death from the controller); it leaves when its
  request pipe closes OR its parent is no longer the process that made it (asked every second); `stop` kills one
  that has not left within three seconds. A dead zygote costs no verdict: the worker makes that fork and every later
  one itself, said once on stderr.

ORPHANS, HOW TO LOOK (a zygote shows the same way as a fork — its command line is its worker's; one whose worker
died is gone within its one-second poll):
`ps -axo ppid,etime,command | awk '$1==1 && (/ctypes/ || /pytest/ || /sys\.stdin\.readline/)'`
— a fresh-interpreter child shows as `python -c ... ctypes ...`, a fork as its worker's own command line (xdist's
`python -u -c import sys;exec(eval(sys.stdin.readline()))`, or `python -m pytest ...` run serially). The older check
for `/ctypes/` alone cannot see a fork. An entry there younger than ten seconds is a fork inside its alarm; anything
older is a real orphan (measured: a worker killed mid-fork leaves one line, gone at the alarm).

THE PUBLIC PIECES for a battery whose machines are the ROM's own calls — ONE family in `aes_event`, bound once per
battery (`aes_evasync`, `aes_evlib`, `aes_evinput` each bind one and keep module-level `watched` / `scenario` /
`cases` / `at` names; a new battery binds its own and invents none of this):
- `aes_event.Layer` — a battery's routines: their entries and frames, what a machine leaves out, which argument is
  RESTAGED out of its caller's stack (`restaged=`: a pointer into the stack band, which a machine keeps nothing of —
  ap_rdwr's QPB, the rectangle w_setactive hands ct_chgown), which end a run may return before. Its watch is
  `EntryStops`: the ROM's own run of a scenario stopped at each entry, so a case is "the ROM's own call, at the
  machine and with the frame the ROM makes it" (an ARRIVAL, `LayerArrival`). `ends=` / `once_past=` end a run at a
  PC once another has been passed — refused by name where the run would end having executed nothing. KNOW WHEN AN
  ENTRY IS WATCHED AGAIN (`EntryStops`' docstring): the entry arrived at is unarmed until the run's next stop, so a
  recursive entry's inner arrival and a second process's call of an entry whose first caller parked inside it can
  be missed.
- `aes_event.Scenarios` — the DECLARED arrivals of each scenario, each run held to them once per process (what holds
  a watched run to what it saw), with `cases` / `case_id` / `arrival` / `nth_of` / `at`.
- `aes_event.as_pokes(memory, over, without=, upto=)` — an image as the pokes that make it over another (the stack
  band left out by `without=`), block-wise: how an arrival's machine is kept.
- `aes_event.dispatched(pokes, pd, comes_out_at, alone=)` — the dispatcher's own loop run until process `pd` comes
  out at a PC, alone on the ready list unless the case says another is ready too: the one spelling of "woken by the
  scheduler". `aes.list_of(image, head, link, limit)` is the one linked-list walker.
- THE INTERRUPTS ARE SPELT ONCE — `aes_event.Interrupt`, `PRESSING` / `RELEASING` / `CLICKING` / `DOUBLE_CLICKING` /
  `RIGHT_PRESSING` / `moving_to` / `moving_by` / `ticking`: sequences over the machine as it goes — and taken by two
  runners, in place (`taken_in_place`: `press`, `move_to` …) and watched (`aes_evinput.taken_watched`); every
  sequence leaves one machine under either.
- `aes_event.settled_where_stored` + `MASK_WORD_AND_SPL` settle a row's dropped words from one run;
  `run_core_steered` is the trial loop of a case whose reason steers only some cases (above).

AN INTERRUPT TAKEN BETWEEN TWO INSTRUCTIONS — the fourth surface. No differential row interleaves: Tier 1 and Tier
3 run a routine from its entry to its return with nothing between two of its instructions, and the plain C is the
same function in every one of them. So a word an INTERRUPT also writes is invisible to all of it, on target only:
the ROM counts with ONE instruction on memory (`subq.w #1,$c906`), GCC makes load / change a register / store of
the same C, and an interrupt landing in that window is overwritten (forker's count: an event stranded, everything
after it one late). The procedure for a routine that reads or counts a word an ISR shares:
- WHEN A ROUTINE NEEDS IT: it runs at process level (or in a lower-priority interrupt) and touches a word an
  interrupt also writes — the audit's eleven: the fork queue's head, tail, count and posted byte, the click
  counter's three words, the buttons as last seen, the tick's two longs, `$c84e`
  (`test_aes_evfork_interrupted.SHARED_WORDS` is what the sweep's states compare, with the posted byte and the whole
  ring). Audit by MEASUREMENT: the denominator is the ROM's
  complete reference list of those words (`linef_dis.py` over the whole GEM range), each site read as the ROM's
  instruction, ours on target, whether an interrupt writes it; a site in no reconstructed routine is named as such.
- THE IN-MEMORY IDIOMS (`include/m68k_idioms.h`): `add_word_in_memory(image, at, n)` / `sub_word_in_memory` — on
  target ONE instruction whose operand is the word in memory (gas makes `addq` / `subq` of a small constant, the
  ROM's own opcodes), off target the plain C; and `word_read_again(image, at)` — its own `move.w` from memory — for
  a word an interrupt writes that the ROM reads a SECOND time with no call between, which GCC folds into the first
  read. Where the ROM is itself racy, MATCH THE ROM and say so (STATUS, KNOWN ROM RACES): the window is neither
  closed nor widened.
- THE SURFACE (`test/test_aes_evfork_interrupted.py`): the routine run once per instruction boundary of its own
  body — on the ROM and on each blob — with the ROM's own interrupt glue taken AT that boundary by the 68000 itself
  (the instruction there replaced for one step by a `jsr` to a trampoline that saves SR and the scratch registers,
  calls the glue and returns onto the replaced instruction; the watch steps by the successors the routine's own
  disassembly names, a successor the listing misses refused by name). THE RULE: the SET of states ours can be left
  in equals the set the ROM's is left in at the boundaries of its own, and a state the ROM is left in at ONE
  boundary alone is left by ours along one straight line of instructions. A new routine that touches a shared word
  gets a case there (routine × the ROM's interrupt).
- AND WHICH INSTRUCTION COUNTS (the same file): each of those routines is also stepped with NO interrupt, on the ROM
  and on both blobs, and every change its own instructions make to a shared word is read off the instruction that
  made it — COUNTED IN MEMORY by one instruction, or STORED. Ours make the ROM's changes, of the ROM's kinds, in
  the ROM's order (`COUNTED_BY`: which words each routine counts, held to the ROM's own run). This half does not
  depend on where a case's interrupt can land: two sites were memory-direct by GCC's own choice, and nothing held
  them. A count added to a new routine goes in `COUNTED_BY`.
- WHAT IT DOES NOT HOLD: it lays the interrupt whatever the IPL, so a routine that MASKS (an spl7 bracket) is not
  its to hold — the bracket is Tier 3's symmetric SR rule's; and it takes no boundary inside a callee.
- A MUTANT OF TARGET TEXT (an instruction's shape) is swept on a private BLOB: no host `.so` can kill it.

The door also never lays back the nested run's write to the Line-F mask word `$cc44`. A caller's own non-empty masked return
rewrites that word after its last door call, so the C's image keeps the word as the C found it.

Three mechanisms are designed and NOT built (the third in part):

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
- **The RELOCATION of a ROM-made fork queue for our blob.** forker's `jsr (a0)` itself is BUILT (`aes/evfork.h`,
  band 4 wave 1): it is `staged_call.h`'s `call_alcyon_pointer` — the ONE register-carrying hook, bound by a case
  to the candidate's fork functions by their ROM addresses (`aes_evinput.HANDED_ROUTINES`; the VDI's
  `$fcff0a` default_user_cur among them for a playback); on target a queue entry's code is the function's own
  plain-C entry (`aes_<fn>_fork`), and a row whose run QUEUES one drops that code long at Tier 3 by name
  (`aes_evinput.queued_code_drops`, derived from the ROM run's own stores). What is not built is laying a queue the
  ROM's ISRs filled into OUR blob with its code longs relocated — which forker's own pricing waits on. Every forkq
  caller queues a fork function by an IMMEDIATE ROM address (pushed, or — ap_tplay — stored in the local its forkq
  call pushes), and forker's recorder and ap_trecd compare against them: sixteen instructions,
  `aes.FORK_FUNCTION_IMMEDIATES`, CODE values a C port stores as the ROM's and a rebuilt ROM as its own
  (`test_aes_door` holds them as every longword of the GEM text naming a fork function, and every forkq call as
  queueing one).

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

**The table is measured over every core.** `bench/tier3.py --out` spreads its measuring pass over `--jobs` forks of
itself (default: every core; `--jobs 1`: one process, row after row), taken after the registry is imported: a
session's sliced rows are one share (one pair of runs prices them all), every other row its own; the table is judged
and written by the parent from the measurements in ROWS' order, by the code that judges a serial pass. THE TABLE IS
THE SAME, LINE FOR LINE, whatever the count (`test_tier3.py` holds it). A fork that DIES measuring — a segfault of
the oracle, an out-of-memory kill — ends the pass by name with no table, as does a pass no share comes back from
(`test/fork_pool.py`: a `multiprocessing.Pool` waited for the lost share for ever, and `make bench` is every
gate's prerequisite), and the pass is held to the rows it was asked for.

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

**THE SWITCH is a third kind of `.S`** (`atari/target.mk`: `SWITCH_SOURCES`; `src/aes/switch.S`): the process
switch's hand 68000 — today dsptch's twenty bytes, `$fe387c..$fe388f`, byte-exact, its `jmp` to the ROM's own disp
until the scheduler ships. It is not a table row: there is no C twin to exclude and no thunk may stand over an entry
that builds a frame from its caller's return address; its entry carries the name the C calls (`aes_dsptch`), and the
headers it includes are assembler-safe (`__ASSEMBLER__` guards in `aes/switch.h` / `aes/evsync.h`). `test_tier3.py`
pins the list (as make expands it), the bytes on both blobs, and that C calling `aes_dsptch` links against it under
both blobs' flags; `transcription.switch_sources()` / `SWITCH_ENTRIES` are the Python side.

**An ALCYON ENTRY `.S` is glue, not a transcription.** When AES C hands a routine BY VALUE to ROM-shaped code that calls it
the Alcyon way — ob_draw passing just_draw to everyobj (`$fea08c`) — the host case binds the ROM address to the C core, but
on target the value must be our own routine: the ROM's would run the ROM's AES code inside our build, which the (V) bench
refuses by name, and a rebuilt ROM would not hold. `src/aes/obdraw.S`'s `aes_just_draw_alcyon` repacks everyobj's 10-byte Alcyon
frame into the GCC call (the image base, then each word sign-extended into its slot) and enters the C core. It has no ROM
bytes and no row of `include/transcribed.h`: `atari/target.mk` lists it as ALCYON_ENTRY_SOURCES, filtered out of
TRANSCRIBED_SOURCES so the transcription `.globl` pin stays exact; Tier 3 counts its cycles as glue (`bench/tier3.py`'s
ALCYON_ENTRIES, T→G, like a generated thunk); and `test_transcribed.py` pins its `.globl`s to exactly that list, outside the
table. No host surface sees it, so its mutants are judged by Tier 3's second differential.

## How the suite is spread over the workers

Every run under xdist is distributed by `--dist worksteal`: `test/conftest.py`'s `pytest_configure` sets it wherever
the command line names no `--dist` of its own — so `make test`, `make guarded` and every `PYTEST_ARGS=` override
(`-n4 -k fuzz`) get it, a run that asks for another mode keeps its own, and a run with xdist off (`-p no:xdist`, a
mutation sweep's) is left alone. It is not a makefile `PYTEST_ARGS`, which an override would replace. xdist's default
`load` hands each worker a contiguous run of tests up front, and this suite's cost is not even: one file of whole
file-selector sessions is seconds a test where most are milliseconds, so one worker ran it alone while the others
idled. `worksteal` lets an idle worker take the tail half of the longest queue.

`test/conftest.py` also fixes the COLLECTION ORDER worksteal acts on. A session is derived once per PROCESS and its C
runs in one child per process, shared by that session's cases; collected in pytest's own order (every session through
one test function, then every session through the next) the cases of one session are a file apart, and a steal sends
the far ones to a worker that derives the session again. So the cases of one session are collected back to back, where
the first of them stood. WHICH cases are one session's is the battery's to say, by the marker `collected_with`: on a
test (`collected_with(name)`) or on a module (`pytestmark = pytest.mark.collected_with(by=function)`, a function of a
case's parameters answering its group, None for a case that is no session's). Three batteries declare it: the file
selector's sessions (`test_aes_fs_input.py`), its priced sessions' cases (`test_aes_fs_input_rows.py`), and Tier 3 —
a sliced session's rows, companions and partition test (`test_tier3.py`). Nothing is added, removed or renamed — the
same items and ids, reordered inside their own module. `test/test_conftest.py` pins both: the distribution on real
runs of xdist, the order on each battery's own declaration.

## ROM-only derivations kept on disk — `test/derived.py`

A battery's machines are DERIVED — the ROM's own runs: a scenario watched at a layer's entries, a file-selector
session over the staged disk, the one run that says whether a row's routine stores the Line-F mask word. A
derivation runs no line of the reconstruction, so every process of a run made the same ones again: 25 CPU-seconds
of every process's import (each xdist worker of both suites, and the bench). `@derived.kept` keeps a derivation's
answer under `build/derived/` and serves it to any process that asks the same question.

A STALE ANSWER CANNOT BE SERVED, because "the same question" is CONTENT. WHAT KEYS IT:
1. THE TREE — the digest of every file a derivation could read or be made by (every `test/`, `bench/`, `tools/`
   Python file, every header and source, `aes_map/`'s decoder, the kit's Python and the workspace tools it imports,
   its oracle library, the ROM, the boot snapshots, the makefiles, and the candidate `.so` AS THIS PROCESS LOADED
   IT), with the interpreter's version and whether it runs its `assert`s (`-O`): any edit, a comment's included, is
   another tree;
2. THE BASE IMAGE in force (`harness.set_base_image`: the sweep over other captures derives for itself);
3. THE DERIVING FUNCTION, read as a value (two closures of one `def` are two derivers);
4. ITS ARGUMENTS BY VALUE — tuples, named tuples, a function by its code, defaults, attributes and what its closure
   holds; a schedule (`aes_event.Waits`) by what it says it is asked about (`derived_content`); a machine's POKES by
   the image they make — runs that do not overlap in address order, runs that OVERLAP in the order they are laid
   (`make_image`'s: the same runs laid the other way round are another image, and another question). An argument
   of any other kind is REFUSED by name.

THE KEY NAMES THE TREE THE PROCESS IS MADE OF — the part no digest gives, because agents edit this tree while runs
are in flight and a process is the files it has ALREADY read (measured before this rule: an edit 0.3 s into a
worker's life was keyed as the new tree by a process running the old helper, and its answers were served to every
later process of the edited tree). Four halves, each with its RED in `test_derived.py`:
- WHEN THE PROCESS BEGAN is asked of the kernel, and a file of the tree that changed SINCE — by its modification
  date or its inode's — puts the cache out of use for that process's whole life (it derives everything, keeps
  nothing; said once on stderr, with the file). A process that cannot be asked (anything but Darwin) keeps nothing;
- THE FILES ARE STAMPED AS `derived` IS IMPORTED, and it is imported FIRST (`conftest.py`'s first import, the
  bench's): the key's bytes, read later, are those stamps' bytes or there is no key;
- BEFORE EVERY WRITE the process asks again, exactly: every file as stamped, none added or gone, and NO MODULE OF
  THIS REPOSITORY IMPORTED THAT THE KEY DOES NOT READ (`derived.unkeyed_modules`: the patterns are held to what is
  really imported — four imported modules were in no key; a new one puts its importer out of the cache by name);
- BEFORE A READ the same at a read's price: at once when a module was imported since the last time (code read off
  the tree as it is now), every file's stamp again every 50 ms.

Beyond the key:
- EVERY KEPT ANSWER IS HELD TO ITS DERIVATION, a sample a run: each process makes a few of the answers it is served
  AGAIN, the cache off, and holds them equal (`derived.SAMPLED_AT_MOST` a process, chosen by the key, the worker's
  name and `AES_DERIVED_SAMPLE_SEED` — other answers in each worker, the same ones for the same tree). A kept
  answer nothing ever makes again is where a run-order dependence of the oracle would freeze (the user stack
  pointer's was found by processes that each derived for themselves); one that is not what the ROM derives now ends
  the process that found it, BY NAME. The run's last lines say how many were made again
  (`derived: N kept answers made again and found equal, in M processes`);
- THE MONKEYPATCH RULE: a test that takes `monkeypatch` DERIVES EVERYTHING ITSELF AND MAKES ITS OWN FORKS
  (`conftest.py`, autouse) — a patch can change what no key sees (a module's budget, a counter on the runs made),
  and the zygote froze every module as the session started, so a patch on the fork's side is never its fork's
  (`aes_event.ZYGOTE_SIDELINED`; a test that means the zygote while it patches the worker's side puts it back). A
  test that patches or counts ROM runs WITHOUT the fixture switches the cache off itself (`derived.DERIVED_OFF`);
- nothing is kept for a process whose candidate is not `build/lib*.so` (a mutation sweep's private library);
- a file is written whole under another name and renamed, and CARRIES THE DIGEST OF WHAT IT HOLDS: one that will not
  load, or does not hold what its digest says (one flipped bit), is made again;
- a derivation that leaves something of an ARGUMENT beside its answer says so IN its answer (`aes_event._deliveries`
  answers how far the run counted its schedule, and the schedule is put there on a hit too);
- a derivation must answer ONE machine whatever ran before it in the process — which is why the kit seeds USP at a
  run's entry (`TRAP_MODEL.md`) and `test_a_derivation_answers_one_machine_whatever_ran_before_it` pins it here.

TO KEEP A NEW DERIVATION: decorate the function that makes the ROM's run with `@derived.kept`, hand it everything it
reads as arguments of a kind the key can read (a module global a test may patch becomes an explicit input), and add
its changed-input cases to `test_derived.py`. NEVER keep anything our build takes part in — a differential, a Tier
3 measurement, the bench blobs' runs: that is the suite's subject. And the real-disk run's DELIVERIES are not
reused for a session's replay: they are another machine's wherever GEMDOS itself left a mark an interrupt meets (a
session that rings the bell: the BIOS's sound state under the next key's click), and a delivery records the bytes
an interrupt writes over, not those it reads — so "they fit" would not prove "they are the replay's"
(`test_aes_replay_machinery.py` holds both halves). The replay's own deliveries are kept by content instead.

HOW IT IS RUN:
- `make derived` (`python test/derived.py`, a prerequisite of the table and of both suites) imports the test modules
  over every core, fewest-imports first, so the bench and every worker are served: 17 s for a new tree, a tenth of
  a second for one already made. A bare `pytest` with nothing made first derives in every worker. A fork of the
  pass that DIES ends it by name (`test/fork_pool.py`), and `make` with it — it does not wait for ever.
- `make clean` removes `build/`, the cache with it. It holds 16 MB a tree; the six most lately used trees are kept
  and one unused for two days goes.
- THE SWITCHES, all environment variables: `AES_DERIVED_OFF=1` (nothing read or written: the cold shore of any
  A/B); `AES_NO_ZYGOTE=1` (no process forks a zygote: every guard's fork is its worker's own, the other A/B);
  `AES_DERIVED_SAMPLE_SEED=<anything>` (another sample of the served answers is made again). INTERNAL, never set
  by hand: `AES_DERIVED_TREE`, a process's tree key and the record it was made with, handed to its children.
- TELLING A COLD RUN FROM A WARM ONE: collection is 36–40 s a worker cold and about 10 s warm (pytest's own wall:
  210.3 s for a bare cold `pytest`, 173.9 s for the pytest of a cold `make test`, 155.3 s warm — quiet, ten
  workers). A timing quoted without saying which is not a timing; for a cold figure empty `build/derived/` or set
  `AES_DERIVED_OFF=1`, and remember that ANY edit under the keyed tree makes the next run cold.
- WHAT MUST STAY EQUAL cold, warm and off (the content-neutrality check of any change here): the collected case ids
  and outcomes, the row hashes and scenario hashes over one pinned `boot_ram.bin`, the table's lines.

## `make gates` — the pre-commit gates as one command

`make gates` builds once (libraries, both blobs, snapshot, derivations, table) and then runs `make test`'s pytest,
`make guarded`'s pytest and the ROM build (`make -C atari -B all`) SIDE BY SIDE, each with its own log
(`build/gates/<gate>.log`), its own status file and its own pytest cache; it prints each one's last lines and ends
non-zero if any did. The same command lines as kit.mk's targets (PYTEST_ARGS / GUARDED_PYTEST_ARGS apply), the same
case ids and outcomes as the four run in turn. It starts by removing `build/gates/`, so two of them at once in one
tree overwrite each other's logs: one at a time. WHAT IT BUYS IS NOT THREE GATES FOR THE WALL OF ONE — the two
suites are the same CPU-bound work twice and ten cores are ten cores (side by side each takes about twice as long):
measured, 388 s against 389 s for the four in turn (309 s with the derivations made). It buys one command, one build and one set of derivations. It
does not `rm build/*.so`: the forced rebuild before a commit is still the committer's own first step.

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
* **Python machinery is swept in a PRIVATE MIRROR of the tree** (the tree's own files are never mutated): recreate/,
  the kit, the ROM, its own `build/` — and its own derivation cache, which a mutated file makes another tree's
  anyway.
* **Do not pass `-x` under xdist**: `-x` ends an xdist run with exit 2 (interrupted), which the strict rule counts
  ABNORMAL though a test FAILED. Serial runs take `-x`.
* **A mutant that breaks a battery's IMPORT is an ERROR, not a FAILED test** — every battery registers its rows at
  import, through the helpers. The helpers every import stands on are held where no battery is imported
  (`test_aes_event_helpers.py`), so such a mutant fails there by name.
* **A mutant of TARGET TEXT** — an instruction's shape, which the host `.so` compiles to the same function — is swept
  on a private BLOB against the surface that reads the blob (`test_aes_evfork_interrupted.py`, the byte pins).
* **A twin's leaf battery is swept ALONE**: a mutant another battery kills is still a hole in the battery that is
  the twin's only holder once its entry is flipped.

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
├── test/               the differentials; `harness.py` is the kit shim plus `addrs`; `conftest.py` the
│                       distribution over xdist's workers (worksteal), the collection order, each
│                       process's zygote and the monkeypatch rule; `zygote.py` (who makes a guard's
│                       fork), `derived.py` (ROM-only derivations kept by content) and `fork_pool.py` (a
│                       pass over forks that ends, whatever a fork does)
├── tools/              boot_snapshot.py (the snapshot), addrs.py (addrs.h as Python)
└── build/              gitignored: the candidate .so, the RAM snapshot (the ROM's own data),
                        bench/ — the cross-compiled blob and the Tier 3 table — and bench_shipped/,
                        the shipped configuration's blob and its generated glue; derived/ (the
                        derivation cache, by tree) and gates/ (`make gates`' logs)
```
