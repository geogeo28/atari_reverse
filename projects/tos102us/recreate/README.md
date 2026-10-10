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

**The mask is what those three boots showed, not a bound — "bit-identical outside it" is false in general.** Over
three later captures 32 bytes outside it moved (`$1459` +11, `$8920` +14, `$9fa1` +3, `$a075`, `$a098` +4, `$a24a`
+2, `$c7e9`), a fourth showed `$754e` +2, `$95ba` +4, `$9707`, `$1662` +2, and `savptr`'s frame lies at `$93a` or one
46-byte frame lower: the same phase-of-the-idle-work class at the edges of the regions above. The mask and the
capture are unchanged; what follows from it is the rule the gate enforces — every test holds over a FRESH capture, and
a number a capture decides is derived, never pinned.

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

## The pre-init machine and the ROM's own boot

Band 5's subject is what the snapshot lies AFTER — the AES's init, the accessory loader, the shell — so it has two
more kinds of machine, both made by ROM runs and neither by a poke (`tools/preinit_snapshot.py`,
`tools/accessory_disk.py`, `test/aes_boot.py`, `test/test_aes_boot.py`).

```
make preinit        # build/preinit.bin      — the snapshot's machine stopped at gem_entry, blank floppy     (~4 s)
make preinit-acc    # build/preinit_acc.bin  — the same stop, the test accessories' floppy in A: from power-on (~4 s)
python tools/preinit_snapshot.py --twice          # capture twice, report what differs
python tools/preinit_snapshot.py --cross-check    # OPT-IN: the accessory machine against a real Hatari boot
```

**A pre-init machine** is Hatari stopped by `b pc = $fd9eca` — `gem_entry`, before one instruction of GEM — on the
snapshot's own machine (arguments, ROM and blank disk read from `boot_snapshot`, which is untouched). The file is the
megabyte of RAM, THE REGISTERS (PC `$fd9eca`, SR `$0300`: user mode; both stack pointers; every data and address
register zero but D0 = A6) and the shifter's palette and resolution byte as the debugger reads them. The capture is
refused unless the PC is the dump's own `exec_os` and the CPU is in user mode. Both files are prerequisites of
`make test` / `guarded` / `gates`; their names are outside every pattern of `derived.py`'s tree key, and they have a
content stamp of their own (`build/preinit_inputs.txt`), so neither capturing them nor an edit to their constants
ever re-captures the snapshot or moves a kept derivation.

**A booted machine** is the ROM's OWN `gem_entry` run in the oracle FROM a pre-init machine — entered with the
capture's whole register file, in user mode, on the capture's stacks — to THE DESKTOP'S FIRST IDLE: the first arrival
at idle's poll with nothing ready, nothing woken, no fork queued. GEMDOS, the BIOS, the XBIOS, the VDI, Line-A and
Line-F are the image's own code through the image's own vectors. `desk_machine()` boots the blank disk's capture
(592,893 instructions); `accessory_machine(first, second)` the accessory disk's (714,383 for the quiet pair), each
accessory in its mode. Kept derivations (`derived.kept`), keyed by the pre-init machine's CONTENT: 0.25 s / 0.59 s
cold, 11 ms served.

**What the oracle serves for that run — the device model** (a boot that meets anything else is refused by name):

1. **The floppy, at the ROM driver's three entries** (the addresses the machine's own `hdv_bpb` / `hdv_mediach` /
   `hdv_rw` hold). The run is stopped there and answered: `Rwabs` copies sectors between the caller's buffer and a
   720 KB image held OFF the machine; `Mediach` says UNCHANGED, always; `Getbpb` is never asked (refused by name).
   The disk served must be THE DISK THE CAPTURE BOOTED WITH — the driver's own record must hold its BPB and its
   serial, or the boot is refused. The driver's private scratch and timers are not advanced.
2. **The blitter probe's bus error.** XBIOS `Blitmode`'s probe (`$fc0f1a`) touches `$ffff8a00` behind a bus-error
   vector; the oracle's CPU takes no bus error and the read is of an unmodelled I/O byte. The run is stopped at that
   one instruction (`$fc0f34`) and the exception taken as a 68000 takes it: the 14-byte group-0 frame pushed, the PC
   from vector 2, no data register touched. What that buys is the machine's own path through the probe, not its
   answer — this call (`Blitmode(-1)`) discards it.
3. **The shifter, by declaration**: the sixteen palette words (`vq_color` over every pen; they land in
   `LINEA_REQ_COL`) and the resolution byte (twice), each as the capture read it out of Hatari.
4. **The keyboard ACIA's status**, by the kit's own model: seven polls, one before each of the seven IKBD bytes the
   mouse set-up sends (`$08`, `$0b 1 1`, `$10`, `$07 0`), which are dropped as every off-image store is.
5. **One interrupt, the horizontal blank.** `gem_main`'s `sti` is `andi #$f8ff,sr`; on the machine the ROM's HBL
   handler then raises the interrupted mask to 3, which is why every SR the AES saves reads `$23xx`. One level-2
   interrupt is held pending for the run (`m68k_set_irq`), taken through the image's vector, served by the ROM's
   handler. Every boot takes exactly one.

NO OTHER INTERRUPT IS DELIVERED: nothing between `gem_entry` and the first idle waits on a clock. **No time passes** in
a booted machine — its clocks are its pre-init machine's, and `colorptr` (`$45a`) is still pending: the first
vertical blank delivered to one loads the palette.

**Why the disk is in the drive from power-on, and not a RAM disk.** `Pexec` hands a program the LARGEST free block and
CLEARS it; at the accessory loader's `Pexec(3)` that is all of free memory, a staged RAM disk and its stubs with it
(measured: the run left the rails). So the disk is a device off the machine. And it is NOT swapped in at `gem_entry`:
a first version did that (Mediach "changed" once), and against a real boot 821 bytes differed — GEMDOS's two sector
buffers, its directory records, each basepage's current-directory byte. With the accessory disk in Hatari's drive
from power-on, GEMDOS's cache and the driver's record are the real ones. One capture serves every mode pair because a
mode is one word inside an accessory's own cluster: `accessory_disk.disk_of` builds the image from the UNPATCHED file
(so `st_build`'s content-derived serial is one serial) and patches the word in the image — every byte outside the two
mode longwords is equal for every pair of the modes any battery boots (a test, which reads the modes off the batteries' own machines).

**The test accessory** (`test/acc/testacc.S`, linked by `test/acc/acc.ld`, wrapped by `atari/mkprg.py`): `appl_init`,
then a wait for ever. `QUIET` waits in `evnt_mesag`; `FIND` does `appl_find("TESTACC2")`; `WRITE` an `appl_write` of
16 bytes to what was found (or to pid 0, the desk); `MULTI` waits in a six-way `evnt_multi` — for TWO clicks with `DOUBLE` (band 5 wave 2: a second process in a
multi-click button wait beside the desk, which is what brings the AES's count of them, gl_bpend, above 1). It keeps every answer of
the AES in its own DATA, which a test reads through the basepage the PD names. SINCE BAND 5 WAVE 1 (the screen
manager's handlers need a window with gadgets and an entry of the desk menu, and both must be a real process's own
calls): `REGISTER` does `menu_register` (an entry of the desk menu, which the screen manager answers with AC_OPEN);
`HIDE` answers that AC_OPEN with `menu_bar(0, 0)` (the one way a machine comes to have no menu while its screen
manager runs); and `with_a_window(kind, mode)` makes it `wind_create` a window of GEM's gadget bits `kind`, name it,
give its sliders a size and a place, and `wind_open` it before the wait — at a rectangle of its own by its id, so two
accessories' windows overlap and each keeps its gadgets in view. It answers no message: what the screen manager sends
it is read and dropped. A MODE IS A LONGWORD of the accessory's text (`acc_kind`, then `acc_mode`), patched in the
image as the word was: the disk is still one disk to the machine whatever the pair (the test, over every mode a
battery's machine uses). THE FILE IS 1,010 OF THE 1,024 BYTES OF ONE CLUSTER — `accessory_disk.disk_of` asserts it fits,
and `file_at` assumes one: 14 bytes of room before a mode more needs that generalised.

**How the machines relate to the boot snapshot.** `desk_machine()` is the snapshot's own boot met at its FIRST idle
instead of nine hundred vertical blanks on: the vectors, the whole TPA (but the Line-F mask word and the AUTO
runner's ABANDONED STACK — 128 bytes derived from the machine's own pointers, dead on both shores), both processes'
PDs and saved contexts, the lists and the screen are equal, and that is a test. Byte for byte they differ in 369–425
bytes, 56–62 outside `boot_snapshot.MASK` — clocks, `colorptr`, the floppy's VBL words, `savptr`'s last frame,
interrupt frames left on stacks, a few tick-driven AES words — which is NOT pinned: a capture's phase decides it.
`accessory_machine()` is the desk's plus its accessories (same static PDs, same CPU registers, same screen).

**`--cross-check`** (opt-in; no suite or gate runs it) boots the accessory disk in Hatari to the desktop by the
snapshot's own procedure and prints what the accessory machine differs from it in, outside both masks. Measured
2026-10-09, the quiet pair — 109 bytes in 14 runs, none of them a process, list, basepage or GEMDOS record:

| where | bytes | what |
| --- | ---: | --- |
| `$45b` | 3 | `colorptr`, still pending |
| `$92e` | 6 | `savptr`'s last frame |
| `$a4a`, `$1696`, `$16ab` | 2 + 1 + 21 | apparently the real driver's scratch from the sectors it read (inferred) |
| `$8920`, `$8c00` | 14 + 10 | dead frames: `gem_entry`'s first stack, the dispatcher's |
| `$954d` | 5 | the tick glue's stack (no tick ran) |
| `$9f5f`, `$a318`, `$a759` | 70 + 5 + 23 | interrupt frames in the static UDAs' stacks |
| `$11bb4`, `$11bca` | 4 + 5 | the same, in the second accessory's UDA |
| `$cc45` | 1 | the Line-F mask word |

**Capture-phase facts, and the second mask.** Unlike the snapshot, a pre-init capture's CLOCKS move: it stops at an
instruction, and when the boot reaches it depends on the emulated disk's rotation (`_hz_200` 396..450 over eighteen
captures). `preinit_snapshot.MASK`: `_vbclock`/`_frclock`, `_hz_200`, the floppy VBL service's words (`$9f8`), the
timer-C divider, dead frames of the OS stack (`$1455`..`$1676`), GEMDOS's 20 ms accumulator, the floppy driver's
scratch (`$74b8`), `GEMDOS_TIME`, the 50 Hz millisecond count, and THE AUTO RUNNER'S ABANDONED STACK (`$ca82` +128:
the BIOS's AUTO runner searches `\AUTO` in supervisor mode on a stack at the top of its own basepage, then abandons
it — `$fc0d42 lea $755a,sp` — so whatever an interrupt pushed there stays; one capture set in six of a gate had a
level-6 frame in it, which made the family test red until the span was left out and noise-proven). Registers, palette and every byte outside it agreed
in all eighteen — but two regions were first seen at the tenth and twelfth capture, so it may be incomplete, and no
test depends on its completeness. What IS a test: booted from a pre-init machine whose every masked byte is NOISE,
the ROM takes the same instructions to the same registers and the same machine outside the mask.
**`boot_snapshot.MASK` is not complete either**: over three fresh snapshot captures 32 bytes outside it moved
(`$1459` +11, `$8920` +14, `$9fa1` +3, `$a075`, `$a098` +4, `$a24a` +2, `$c7e9`), and a byte-exact comparison against
the snapshot went red on a fresh capture — hold a relation to the snapshot by STRUCTURE (pointers, lists, contexts).

**The API** (`test/aes_boot.py`):

```python
aes_boot.preinit(); aes_boot.accessory_preinit()          # the two PreInit(ram, registers, io)
aes_boot.desk_machine(machine=None)                        # Machine
aes_boot.accessory_machine(first=QUIET, second=QUIET, machine=None)
aes_boot.booted(preinit, disk, until=None)                 # the kept derivation -> Boot (ram, registers, ledgers);
                                                           # `until`: stopped at the boot's first arrival at a ROM address
aes_boot.accessory(); aes_boot.accessory_disk_of(*modes); aes_boot.blank_disk()
# a Machine: .ram .registers .boot .pokes ({0: ram}) .image() .waiting() .named(name) .static_processes()
#            .static_uda_bytes() .allocated_accessories() .free_events() .results(process) .accessory_word(...)
```

A row over the accessory machine is run as over the snapshot — its megabyte is the case's pokes. The worked example
(in the suite, both shores): fpdnm finds the second accessory only by its walk of `$c6b2[]`, the arm no machine
before this one reached.

```python
booted = aes_boot.accessory_machine()
staged = case.merge_pokes(aes.leaf_machine(booted.pokes), pp.name_pokes(b"TESTACC2"))
assert pp.run(pp.FPDNM, (pp.NAME_AT, 0), staged).long_answer() == booted.named("TESTACC2").pd
```

CONTINUING A BOOTED MACHINE FROM ITS IDLE WITH INTERRUPTS is built since band 5 wave 1 (`test/aes_gemctrl.py`, next
section: the ROM's dispatcher run from the machine's idle, real mouse packets at its idles and polls, to an arrival).
A MACHINE'S POKES THERE ARE NOT `{0: ram}`: a megabyte in one run covers the harness's own window of free RAM — Tier
3's blob, the staging band, the run's stack and its argument frame (`abi.FIRST_ARG`, which Tier 3 reads BY KEY) — so a
row's machine is the megabyte WITHOUT that window (`aes_gemctrl._as_pokes`: `[0, bench_base)` and from the stack
band's top up, the window held empty below the band where the machine is made, and empty in the snapshot too).
The register entry, the bus error and the IRQ reach Musashi's `m68k_set_reg` / `m68k_get_reg` /
`m68k_set_irq` through `emu._LIB` — accepted for now; a kit accessor is owed.

### A machine whose screen manager is ours — THE TAKEOVER (`aes_boot.booted(..., ours=)`, band 5 wave 2)

```python
blob = isr.blob_named("the bench blob")                    # or "the shipped blob"
m = aes_boot.desk_machine(ours=blob)                       # accessory_machine(first, second, ours=blob)
m.idle, m.resumed_in(m.screen_manager())                   # "the ROM's", "ours"
w = m.continued(aes_boot.mouse_to(136, 5))                 # IKBD bytes through the ROM's ACIA handler, to the next idle
w.observed, w.idle                                         # (("hctl_rect", (136, 5)),), "ours"
aes_boot.compared(rom_machine, m).differing                # [] — and .within: the bytes per class
```

- **What it is.** The ROM's own boot with one change, made at a stop BY ADDRESS — switchto's `rte` about to pop the
  frame psetup pushed for ctlmgr (the screen manager's FIRST ENTRY, vetted there by name): the blob is laid, and the
  two longwords the machine keeps that entry in (PD1's p_ldaddr; the frame's PC) are mapped through the relocation
  registry's entry `aes_event.SCREEN_MANAGER_ENTRY` to the blob's `aes_rom_ctlmgr`, found by symbol. No register is
  set. `ours_of(blob)` refuses a blob with no such symbol.
- **Why at that stop.** On the accessory boot `Pexec` clears the largest free block — the harness's free window, the
  blob's span with it — before the screen manager first runs; nothing stores there after (held on every machine: the
  run's write ledger from the lay on).
- **What such a machine differs from the ROM-booted one in** (`by_nature`, `compared`): four classes, each located
  from the machine's own pointers — the dispatcher's dead frames, the screen manager's saved context, its stack span
  (all three DROPPED: the dead parts noise-proved, the live ones vetted by what the screen manager does when woken) and
  its p_ldaddr (MAPPED) — plus the blob's span. Where the two idle in two dispatchers (the screen manager parked
  last: OUR idle) the whole dispatcher stack is the class, and the Line-F mask word and the BIOS's last save frame
  may be NAMED per comparison (refused where not needed).
- **Which idle ends a run.** A process parks through the dispatcher of the build it runs; the last park decides.
  Every boot ends in the ROM's (the desk parks last); `Boot.idle` / `Machine.idle` says which.
- **`Machine.continued(...)`** receives `mouse_to(x, y)`, `ikbd(header, dx, dy)` and `CLICK_TICKS` through the ROM's
  own ACIA and Timer C handlers and runs on to the next idle. REFUSED BY NAME: a reception the idle's interrupt mask
  would never let in; a machine that never idles (the button held on a menu's item).
- **THE STANDING LIMIT.** The blob lies in memory GEMDOS believes free. A takeover machine CANNOT BE CONTINUED THROUGH
  AN ALLOCATION THAT REACHES THE BLOB — a Malloc or Pexec of the desk's or an accessory's would be handed it — and a
  continuation that stores there, or leaves other bytes there, is refused by name. A case that stages a megabyte
  whose blob text it patched itself (the build's VDI under `trap #2`) hands it through `aes_boot.restaged(machine,
  memory)`: the labelled way.
- **Kept, though it runs the blob**: keyed by the pre-init machine's content AND the blob's (`derived.py` names the
  exception).

### AN ARRIVAL — a routine of another process met where the ROM's own caller calls it (`test/aes_gemctrl.py`)

The screen manager's handlers (`src/aes/gemctrl.c`: ct_msgup, hctl_window, hctl_button, hctl_rect) run in the screen
manager's process, called by its main loop — the ROM's ctlmgr until wave 2. A case of one is never a frame somebody
wrote. It is AN ARRIVAL:

- A MACHINE THE ROM BOOTED (above), its accessories having opened windows and registered a menu entry by their own
  AES calls;
- THE ROM'S OWN DISPATCHER RUN FROM THAT MACHINE'S IDLE (`AES_ROM_DISP_LOOP`, as `aes_event.dispatched` enters it),
  interrupts taken at its idles and at its polls that are no idle exactly as `aes_switch.scheduled` takes them
  (`aes_event.interrupting`: a `chain` `{idle: (interrupt, ...)}`, `at_polls`) — the mouse onto a gadget, a click or a
  press held, a drag, the menu — STOPPED AT THE HANDLER'S FIRST INSTRUCTION, at its n-th arrival there
  (`Arrival(machine, chain, routine, which, at_polls)`, `aes_gemctrl.at`: a kept derivation, keyed by the machine's
  content). A chain that idles with nothing left before the arrival, or that arrives with a delivery still due, is
  refused by name;
- the arguments are the frame the ROM's caller pushed, the machine every byte of RAM there. One arrival is the
  BOOT's own, not a dispatcher's: the desk's menu_bar posts the screen manager a click and the ROM's boot calls
  hctl_button with it before its first idle (`aes_boot.booted(until=)`).

THE DIFFERENTIAL STARTS THERE — the ROM's routine and its twin from that entry, on the harness's stack (the screen
manager's own frames above the entry are untouched by either). A HANDLER THAT RETURNS without a switch (a click: the
button is up again where the screen manager runs) is a door user's differential and a priced row
(`aes_event.run_guarded`, `register`). ONE THAT LEAVES BY THE DISPATCHER is a row that switches, THE SCREEN MANAGER
ITS PROCESS (`aes_event.woken_row`): its own deliveries are numbered from ITS entry — at an idle (a wait that
blocked: a gadget watched, a drag), at a poll that is no idle (the button's rise while the handler YIELDS: it stays
ready, so the machine never idles), or at a door call (below) — and an accessory's or the desk's turn inside it is a
foreign window, the ROM's own code on both shores. What that taught, each held by a test:

- THE DISPATCHER'S OWN DOOR CALLS ARE NOT THE CALLER'S (`aes_switch._Idling.KEEPS_THE_DISPATCHER_S_CALLS_OUT`). A
  button change delivered at a poll while the caller yields BY A DSPTCH OF ITS OWN is posted by the dispatcher's
  forker — bchange's post_button, a door entry. Inside a door call that blocked it was never counted (an entry
  reached inside an open call is no call); outside one the ROM's watched run counted it as the caller's next door
  call, which the C's forker (it calls the entry's core) hands to no door. From the caller's dsptch until disp enters
  a process, no door entry is a stop of a scheduled run. (The rule also took that post_button out of EIGHTEEN
  earlier rows' `Scheduled.calls` — rows that are themselves a door entry, asleep with no call open: none a door
  user's, so nothing compared it; `test_aes_switching.py` holds, row by row, that what the rule leaves out is the
  forker's post_button and nothing else.)
- A HANDLER WHOSE FIRST SWITCH IS ITS OWN DSPTCH, AFTER DOOR CALLS OF ITS OWN (an arrow: the lock let go, the message
  written, then a yield; ct_msgup after its ap_sendmsg) has no byte-for-byte compare AT THE DISPATCHER: no road stops
  a door user's child at a dispatcher it reaches outside a door call (`interrupted` ends at a door call that blocks;
  `switches_where_the_rom_does` forks a core that reaches no door). It is held by the companion's compare of the
  image AT EVERY DISPATCH — a page named, not a byte — and the premise, on the ROM, that the run yields there.
- A SPIN IS TAKEN OUT OF AT A DOOR CALL. A sizer held below the smallest size makes every wait of gr_rubwind return
  at once (the ROM waits for the mouse to leave the CLAMPED corner's pixel): the run never idles and never yields,
  so the button's rise can be delivered nowhere but at a door call's entry (`at_calls`) — a row that takes one
  delivery at an idle and one at a door call, in one derivation.
- A ROW'S OWN BY-NATURE BYTES (`aes_switching.SwitchingRow.also_dropped`): bytes BOTH builds store, each its own.
  At a real arrival the mouse is shown, so the menu's ct_mouse(0) re-shows it and contrl[3] is the ROM's stack word
  (`ctrl.c`'s MISSING ARGUMENT) — the last VDI call of four of hctl_rect's cases (three priced rows, one at Tier 1
  only); each is held to NEED its drop (its companion red in that word without it). Dropped at Tier 3 by name (and held
  to our run's ledger, as every drop is); left out of the companion's end compare AND of its images at every stop
  (`aes_switch.scheduled` / `modelled`, `left_out_beside`), each byte required to be one the ROM's run changed; the
  battery that declares it holds the C's value there, and both censuses count it (`test_aes_event.A_ROW_S_OWN`,
  `test_tier3`'s companion test). Reach for it only where nothing can be staged: the word is written DURING the run.
  `companion(at_stops_only=)` is its narrower sibling for a word a later call of both builds overwrites before the
  run ends (left out of the images at the stops, compared at the end) — REFUSED where the row passes without it.
- A ROW REGISTERED FROM A CAPTURED MACHINE MAKES THAT CAPTURE AN INPUT OF THE REGISTRY'S IMPORT — and so of every
  make target whose recipe imports it (`shipped-glue`, `derived`, the table), not of the suites alone. A tree that
  was ever built hides a missing prerequisite for ever; an empty one dies at the first importer. The Makefile names
  them once (`REGISTRY_READS`) and `test/test_makefile.py` holds that every Python recipe has them. PROVE A SLICE
  THAT ADDS A BUILD INPUT FROM A COPY WITH NO `build/` AT ALL (`make gates`), not from fresh captures dropped into a
  built tree. And keep a machine only UNREGISTERED cases use out of the import (`gadget_arrival_later`).
- A LOCAL THE ROM NEVER SET IS GREEN ON THE HARNESS'S STACK AND NOT ON THE MACHINE'S. The differential enters both
  shores on the run's own zeroed stack band, so a frame word the ROM reads without writing it (hctl_window's x, y,
  w, h for a window that is not the top one) is zero on both — while at the real arrival it is the residue of the
  caller's earlier calls, the same words every time (halves of a ROM and of a RAM address). An arrival is where that
  shows: read what the ROM's NEXT callee is handed there, across several arrivals, before calling a never-set word
  "any value". It is then a DECLARED DIVERGENCE (STATUS), not a fidelity claim.
- ON A BLOB, WHAT A ROW HOLDS WHILE ITS PROCESS IS PARKED IS ITS CYCLE PIN'S ALONE: the image is compared where the
  run ends. A store made before a yield and undone after it is killed on the host at the dispatcher (the
  companion's image at every dispatch) and on the m68k builds only by the exact whole-run cycle count.
- A MACHINE THE ROM BOOTED WITH ITS ACCESSORIES HAS A THIRD PROCESS AND IS NO STAGED APPLICATION: the probe that keeps
  staged applications out of every registry tells them apart by what a loader leaves (`test_aes_pdpipe.py`,
  `an_accessory_the_rom_loaded`: the basepage sndcli parked, the PD's load address).
- THE PRICES' PINS HOLD OVER FRESH CAPTURES — a pre-init capture's clocks move, the cycles of a row over a machine
  booted from it do not (measured over two fresh sets) — but a PD's address is the layout's (an allocated accessory's
  lies where GEMDOS put its block: it moves when testacc.S grows): a premise names processes, never PDs.

- THE TRAP-SAVE EXCLUSION IS THE SNAPSHOT'S FRAME, AND A BOOTED MACHINE HAS ITS OWN. Every wait polls the keyboard
  through the BIOS, whose trap saves its caller's registers under `savptr`; the event layer leaves that frame out of
  every comparison — AT `aes_event.TRAP_SAVE_AT`, one frame under the savptr THE SNAPSHOT was captured with: the save
  area's top between two polls, one 46-byte frame lower where the capture landed inside a BIOS trap. A booted
  machine's savptr is always the top. So over an in-trap snapshot a comparison over a booted machine holds that
  machine's own frame (`$90c..$93a`) byte for byte — the ROM's saved registers against a host core's nothing: 27 of
  wave 1's handler tests were red over such a capture set, as committed. THE RULE: A COMPARISON OVER A BOOTED MACHINE
  STAGES `aes_event.savptr_in_the_band()` (what a registered row's companion and Tier 3 row do already; the
  handlers' returning cases and first halves, whose door images take no named window) OR NAMES ITS OWN FRAME
  (`aes_gemctrl.its_trap_save`, read off the machine's savptr, named only where it is not the snapshot's and cut
  to what the ROM's run stored: the turns). The frame is dead at a turn's start, noise-proven. Other batteries'
  compares over booted machines are not audited for it (STATUS, owed).

### A TURN — the screen manager's loop, both shores from one arrival at its top to the next (`test/aes_gemctrl.py`)

ctlmgr (`src/aes/ctlmgr.c`) is entered by no call and never returns, so nothing of it is a call and its return. What
both shores can run is ONE TURN of its loop, from an arrival at the loop's top (`AES_ROM_CTLMGR_LOOP`, `$fe49f2`) to
the next:

- `Turn(machine, chain, which, at_idle, at_polls, at_calls, chain_polls, budget, staged, also_dropped)`: the ROM's
  dispatcher is run from the booted `machine`'s idle through `chain` to the `which`-th arrival at the loop's top —
  THE START, every byte of RAM kept — and on, ON THE SCREEN MANAGER'S OWN STACK, the turn's own deliveries taken at
  ITS idles, polls and door calls (numbered from the start), to the next arrival. `turned(turn)` answers it as an
  `aes_switch.Scheduled` plus the handlers the ROM's ctlmgr called (read at their entries). One kept derivation.
- THE C'S TURN is `aes_ctlmgr_turn` over that start through the host's model with the door bound
  (`the_c_s_turn`); `held_to_the_rom_s_turn(who, turn)` holds it: idles and polls, every door call's frame in the
  ROM's order (the lock after the wait, let go after the handlers), each call's answer and image where it returns,
  the image at every dispatch, and the whole end image — outside the model's own drops, THE SCREEN MANAGER'S STACK
  (`its_stack`: the UDA's usable 1,196 bytes off the machine's pointers — whole at the stops, at the end only where
  the ROM's turn changed it), the machine's own trap save (above) and the turn's own named windows
  (`also_dropped`: REFUSED where the turn passes without them — the menu's stale count; WM_TOPPED's four stale
  words wherever the write carried them, vetted as the halves of a text and of a stack address).
- `staged`: A LABELLED ARGUMENT CLASS laid at the start on both shores, for what no machine reaches — gl_bpend at
  0, −1, 3 and above (the TWO_WAITERS machine brings it to 2 by itself: `ACC_DOUBLE`), a key in the screen manager's
  own queue (the ROM's nq run over the start: `a_key_in_its_own_queue` says what ROM road was tried).
- THE ONCE-ONLY PART and ictlmgr are met in the ROM's BOOT (`aes_boot.booted(until=)` at `$fe49d2` and `$fe4a6a`);
  the entry itself (`aes_rom_ctlmgr`) is read off both blobs (its frame no more than the ROM's 24 bytes; no return;
  the loop's order) and RUN there from the boot's first-entry machine, the bytes above its stack poisoned, to its
  first dispatch. A TURN ON A BLOB needs a machine whose screen manager is ours: the takeover (`aes_boot`), slice D.

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
STEERING IS ASKED TO A FIXPOINT, ONCE PER TREE — one loop for every layer, `aes_event.steered_as_needed` (under
`run_layer_case` always, and `run_core_steered(fixpoint=True)`). A reason the pass fails without while another is
still named can be needless
once that other is dropped (measured: evnt_multi with a key typed and a press queued — the fork queue's counters), so
after a round that dropped a reason the reasons kept before its last drop are asked again, down to the kit's whole
pass where none is needed; a table that orders its reasons by hand to dodge this is refused in review. THE PLAIN PASS
IS MADE ONCE per case and handed to each trial (`aes.run_function(plain=)`: the ROM's run, the C's and the compare do
not depend on what is asked of the narrowed pass). WHICH REASONS A CASE NEEDS IS KEPT BY CONTENT (`@derived.kept`):
the trials are the dear part — a narrowed pass that FAILS runs the ROM, derailed, to its cap — and every worker that
meets the case, the guarded suite and the next run of the tree would find the same answer. It is the ONE kept answer
that runs the candidate: sound because the tree's key holds the candidate's library as loaded (a private library
switches the cache off), and because it decides no verdict — the run that returns is made every time with exactly
those reasons, and the `AES_STEERED_FOR_NOTHING` sweep asks each (last: 2026-10-07 over `test_aes_evmulti.py`,
`test_aes_evdisp.py`, `test_aes_evlib.py`, `test_aes_evinput.py`, `test_aes_evfork.py`: 1,938 passed). A `certain`
reason is a SPEED HINT (it spares a failing trial a case) and is held by that sweep like any other: `savptr` steers
nearly every call that polls — the sweep found the one case it does not, which opts out by name.

THE EVENT DOOR — the AES's C into the event layer and the scheduler (band 4), which C holds only as far as band 4 has
ported it (REBINDING THE DOOR, below, says how an entry leaves the door). Every C call of one of
their routines goes through ONE wrapper in `include/aes/evdoor.h`, keyed by the routine's ROM address (wave 0: ev_multi
`$fe6998` and ap_rdwr `$fe65c4`; wave 1: tak_flag `$fe4e5a`, unsync `$fe4eb8`, ev_block `$fe6874`, ct_chgown `$fe49ba`,
post_button `$fe52e2`, and ev_multi's two-rectangle shape; wave 2: ev_button `$fe68a4`, fm_button's wait for the rise —
one wrapper, one `ENTRIES` line, one census line each). EVERY ENTRY IS REBOUND (FLIP 3 was the last): the wrapper
calls the entry's C twin, on both builds, and no wrapper is the ROM's call any more — the header has no spelling for
one (the inline-asm `jsr` and the hook's SERVED answer are retired; a `jsr` of our build into the AES's text is
refused by name, `tier3.door_calls`). On the host the wrapper first packs the Alcyon frame big-endian and hands it to
`recreate_call_event_door`, which `test/aes_event.py` binds per case (into the lib the calling process loaded — a
child process binds its own): an ARRIVAL — every frame it is handed compared with the frame the ROM's own run hands
the same entry (MOBLKs and buffers read through their pointers). NOTHING OF THE ROM IS RUN AT AN ARRIVAL, and nothing
of the machine is checked there (WHAT BAND 4 WAVE 3 RETIRED, below: the nested run — the SHADOW — and the hop
checks). One thing differs by nature: the BIOS trap's register save under the keyboard poll (`$8de..$905`, the
CALLER's registers), dropped by name in Tier 1 while priced rows move `savptr` into the stack band. Tier 3 prices
such C on its own cycles as any (V) row, with three rules more — ARRIVALS (our run is WATCHED at the twins, the
kit's `RomBench.measure(watch=)`, and the ORIGINAL's at the ROM's entries: the same door calls, the same frames,
nothing taken off either side), TWO COUNTS and FOREIGN WINDOWS (each below) — and an AES cycle of ours is refused
wherever it is spent. (The mechanism was called (EV) while the door served the ROM's routines and took a window off
both sides for each call; the name went with the windows.)

REBINDING THE DOOR. An entry with a C twin is REBOUND: its wrapper keeps its signature and its callers, and calls
`aes_<entry>(image, …)` on both builds (tak_flag, `src/aes/evsync.c`, was the first). WHICH ENTRIES ARE REBOUND TODAY
IS NEVER LISTED HERE — ask the build: `aes_event.REBOUND` (the wrappers spelt through the macro, read off the
library: all eight) and `aes_event.PENDING` (a twin linked that no wrapper is spelt for: none). On target that call
is the whole wrapper. Off target it is an ARRIVAL first:
- THE HOOK'S ANSWER. The wrapper packs the Alcyon frame and asks `recreate_call_event_door`; the hook answers
  `EVDOOR_ARRIVED`: the frame is recorded for the frames-handed comparison and the interrupt due at that door call
  is laid — then the twin runs over the candidate's image and its answer is reported to a second hook,
  `recreate_event_door_returned`. A wrapper and a hook that disagree halt by name: a hook that knows no twin of the
  entry REFUSES the arrival, and an answer that is neither (what a callback that raised leaves) halts too.
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
  `EVDOOR_TWIN`, no wrapper spelt for it (the way the eight were staged: while one was pending, band 3's C still
  reached the ROM's routine through the door's served road, retired since). The event layer's own C reaches the twin
  by its core (an arrival of nothing: no hook is asked). A pending twin already owes what a rebound one owes — its leaf battery's priced rows, no wrapper
  reached from it — so the day it is flipped nothing is found out.
- HOW A FLIP IS MADE — ONE EDIT. (1) The twin, `EVDOOR_TWIN aes_<entry>(uint8_t *image, <one parameter per frame
  field>)` (`include/transcribed.h`: `noipa`, so GCC neither inlines it into a same-file caller nor clones it, and its
  first instruction stays the arrival point both watches stop at), and its leaf battery, land PENDING and are
  reviewed. (2) THE FLIP is the entry's wrapper re-spelt through the macro in `aes/evdoor.h` (and the include that
  declares the twin) — nothing else by hand: `REBOUND` and Tier 3's lists of door calls follow by derivation.
  (3) Rehearse it first on a private mirror of the tree (host library and both blobs built by the tree's own
  rules): the whole suite, every door-arriving row measured on its own, the table.
  (4) The flip's commit carries the table before and after, every moved row old → new, and STATUS's ratios
  re-quoted from its own `make bench` (`test_status` is red until they are) — BOTH COUNTS of a row whose two differ
  by more than 0.05 (TIER 3: … TWO COUNTS, below). (5) A flip's twin mutants are swept
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
- WHAT BAND 4 WAVE 3 RETIRED OF THE DOOR, AND WHERE EACH GUARD LIVES NOW (step R; STATUS.md's wave log has the
  mutation table). (1) THE SHADOW — until the last flip had stood, every arrival also made the ROM routine's NESTED
  RUN over a copy of the image (`aes_event.nested_run`, capped by `NESTED_RUN_INSNS`), and the twin was held to it at
  its own call: its answer and image where it returned (`vet_the_shadow`), its image at the dispatcher's hook where
  it blocked (`vet_the_shadow_at_dsptch`), 5,473 nested runs a suite run. It was a flip's RED PROOF and a bisecting
  tool, never coverage (next bullet) — and with every flip made and every blocked call continued for real it held
  nothing that is not held elsewhere: a twin at its entry is its LEAF battery's (every arm, swept alone; where it blocks,
  `switches_where_the_rom_does` against the ROM at dsptch); a door user where it blocks is `blocked_then_woken`'s
  first half (the WHOLE image at dsptch, caller and twin both); what runs after is the wake's companion and the
  blob's second differential; and the frames every call is handed are compared at every door call. What went with
  it is WHERE a wrong twin is named: at its leaf case and at the door case's end, no longer at the call in between.
  MEASURED BEFORE IT WENT (50 wrong-twin mutants, strict, before and after): the same 49 killed, one equivalent;
  for 32 the old failures carried the shadow's words; and ONE mutant in fifty the door users' batteries killed by
  those words alone — ev_multi answering the second rectangle's event as the first's, which mn_do does not read.
  ITS SUCCESSORS COST NO RUN OF THE ROM — both shores stop where the shadow compared anyway, the candidate at the
  door's two hooks and the dispatcher's, the ROM's watched run at the address a door call comes back to and at
  dsptch:
  - THE ANSWERS HANDED BACK (`aes_event.vet_the_answers_handed_back`): the word each twin returns (the return
    hook is handed it) held to the ROM routine's D0 where the ROM's own watched run comes back from the same door
    call (`DoorStops.answers`), named by call and entry: "door call N, entry X: the twin answered A where the
    ROM's routine answers B". An entry that answers nothing a caller reads (post_button, unsync: `ENTRY_FRAMES`'
    column) is compared with nothing. It holds, too, the answers of calls that blocked and were woken, which the
    shadow — done at the first dispatch — never did.
  - THE IMAGE AT EACH RETURN, its third field (`aes_event.image_pages`): the RAM as each shore holds it where the
    call comes back, a digest a 16 KB page — "door call N, entry X: the twin left another image than the ROM's
    routine where it returns — in $lo..$hi". What a twin stored and a later call undoes shows there and at no end.
  - THE IMAGE AT EVERY DISPATCH of a door user's modelled run (`aes_event.vet_the_images_at_the_dispatcher`;
    `aes_switch.Scheduled.dispatches`, where the ROM's own process reaches dsptch): the FIRST block is what a case
    ending blocked compares byte for byte; this holds the second and every later one — "dispatch N: the image the
    C holds at the dispatcher is not the ROM's …". (A case ending blocked halts at its first dispatch: it has no
    second.)
  WHAT A PAGE LEAVES OUT, on both shores alike, is one list (`image_pages`), wider than a run's end needs because
  a stop in the middle cannot ask what the ROM's run stored: the stack band, the Line-F mask word, the keyboard
  poll's trap save and frame, every SR save word, and what a road names beside — under the model the caller's
  saved context and the dispatcher's stack ($9c5a..$9c9e and $899a..$8c1a for the shell: its own list, not the
  end compare's); over real GEMDOS its three windows. BOTH LISTS ARE PINNED BY NUMBER, the byte either side of
  each span held red. A QPB'S PLACE (an EVB's parameter whose whole longword is a stack-band address) is left
  out too, but MARKED, not blanked: the digest reads where one was left out, so a stack address on one shore
  against zero on the other is another page.
  WHICH ROADS: in process (`run_event`, and `aes_fslib.run_session` over real GEMDOS), every child `door_child`
  makes (below), and the model's child (`aes_switching.companion`). `door_child(..., door_calls=)` HAS NO DEFAULT:
  a road says WATCHED — the child's frames, answers and images are held there to the ROM's watched run of the
  call — or the `Calls` of a watched run its caller made (fs_input's spinning passes: the ROM's run watched to
  the refused pass, the child saying each call as it goes), or a `HeldElsewhere` with who holds them and why
  (`interrupted` holds them itself, after how the run ended; `run_guarded`'s guard, held by the differential
  that follows; a RED of the child's own binding). An image is taken on BOTH shores or on neither. NOT ON THESE
  ROADS, each said where it is: a case run THROUGH ITS CALLER'S LINE-F WORD takes no image (its two shores are
  staged apart: its direct sibling takes them); a child made by `aes_event.refusal` directly is a RED of the
  door's own machinery; a LEAF's modelled run (no door child) is asked no dispatch image — its dispatcher's hook
  is the C scheduler itself.
  STILL GIVEN UP AGAINST THE SHADOW: the BYTE a red is named by at a stop in the middle (a page is named; the
  end's compares still name bytes) — nothing else that was measured.
  (2) THE HOP CHECKS — the wrapper used to halt where vector `$2c` or the Line-F handler copy's table operand was
  moved. A wrapper is a C call of a C twin, as every other Alcyon call of the AES's C is (none of which ever
  checked the hop); a machine with the hop moved is refused where it shows — the ROM's own run never returns
  (`test_a_machine_whose_line_f_hop_is_moved_is_refused_on_the_rom_s_shore`). (3) `refused_where_the_rom_blocks` —
  a name no battery called any more; the at-dsptch compare it spelt is `interrupted` ending blocked, kept as
  `blocked_then_woken`'s first half. KEPT, each with its reason: `aes_switch.modelled` (Tier 1 of every row that
  switches), `switches_where_the_rom_does` (it bisects a blocking call), `scheduled` (the derivation), the
  dispatcher hook's default refusal, and `Blocked` as an outcome (a transient store made before the block and undone
  after the wake shows at dsptch and nowhere later). One `ENTRY_FRAMES` row per entry decides its frame, its inputs'
  reader and what it parks.
- A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION. A door case reaches an entry only
  in the states its caller makes, and the shadow (retired, above) saw the same states — it changed where a red was
  NAMED, never what was covered (measured at the pilot: five real mutants of the twin that are not equivalent pass
  every door battery, shadow on or off, and the twin's own battery kills all five). So a flip needs the twin's own battery first: its own
  priced rows, entered at the entry itself, reaching every arm, over machines the ROM's scheduler makes —
  `test_tier3.py::test_every_twin_has_a_leaf_battery_s_rows` refuses a twin LINKED without them — rebound or pending:
  the battery is owed the day the twin lands, not at its flip — and "the door cases cover it" is no coverage argument.
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
- A TWIN THAT POLLS AND FORKS (ev_multi: chkkbd's three VDI calls and forker's `jsr (a0)` come before anything else)
  is run through `aes_event.run_layer_case(…, hook=aes_event.EVENT_LAYER_HOOKS)` and, where it blocks,
  `switches_where_the_rom_does(…, hook=…)`: the fork opens the hook itself. Its machines are a running process AND
  what the ROM's own interrupts queued while it was busy (`aes_evmulti.after(machine, interrupts…)`) — the path every
  caller that does not block takes: the interrupt's bytes are in the fork queue or the keyboard's ring when the call
  begins, and the C under the twin posts them. A frame whose last word lies ABOVE `case.STACK_BAND` (ev_multi's is 26
  bytes, the door's widest) is compared at dsptch over the machine WITH the frame staged.
- THE WAITS SATISFIED WHERE THEY ARE QUEUED are how a leaf battery runs a blocking routine's TAIL with no switch at
  all: the fast path refuses (the mouse is another process's) and the wait's own test does not ask (abutton, amouse) —
  acancel, the aprets and their order then run in C in one returning call. What that cannot reach is an answer another
  process or an interrupt posted; say which.
- A BLOCKING TWIN'S TAIL IS HELD BY WAKES THAT REALLY SWITCH (`aes_evmulti.WAKES`, `evlib.WAKES`; band 4 wave 3). A
  routine that waits has two halves: what it writes before dsptch (held AT DSPTCH) and what it does when the
  dispatcher runs it again. The second is A WAKE: the call and a SCHEDULE — what is delivered at which idle of the
  dispatcher the blocked call left by, as `aes_switch.scheduled` takes it — registered as a row that switches
  (`aes_switching.register`; below, "TIER 3: A ROW THAT SWITCHES"). The twin then runs its tail over what ITS OWN
  run made: through the host's scheduler at Tier 1 (`aes_switching.companion`, nothing dropped) and across the real
  switch on both blobs. (RETIRED by that wave: the hook that laid the ROM's memory at the resume under the C —
  `aes_evmulti.woken` / `rom_woken`, host only. No test binds `recreate_dispatch` to a memory-laying hook any more.)
  - BY AN INTERRUPT: the case's interrupts in ONE idle — one delivery, a tuple — the first idle and the only one.
  - A WAKE NEEDS ITS WRITER: a message wait is woken only by another process's appl_write (an interrupt never posts
    one), and the harness's `aes_pdpipe.sent` as the screen manager is no writer a returning run can use (its
    continuation is the run's sentinel). THE WRITER IS THE MENU CHAIN (`aes_evmulti.THE_MENU_CHAIN`,
    `through_the_menu`): the mouse onto a title wakes the snapshot's own screen manager, which drops the menu; the
    mouse onto an item; the press — its own appl_write (mn_do's selection, MN_SELECTED byte for byte) serves the
    parked wait through the QPB of the waiting call's frame. Three idles, and the screen manager's turns are a
    FOREIGN WINDOW. What a case adds comes WITH THE PRESS, in that idle.
  - TWO ROM FACTS EVERY SUCH CASE MEETS. A PRESS BRINGS THE TICKS OF ITS CLICK COUNT (`aes_event.PRESSING`; gl_dclick,
    11 on the snapshot's machine): a short timer runs out with the press, so "a message and a timer NOT run out" needs a
    timer longer than that. THE WOKEN LIST IS LAST IN, FIRST OUT, and a key THAT ARRIVES IN THE PRESS'S OWN IDLE is
    that idle's last fork: it wakes the desk AFTER the press woke the screen manager, the desk runs FIRST and answers
    the key alone — no message is written yet — unless something (the ticks) woke it before the press did. That is a
    fact of what arrives AT ONE IDLE, and no further (next). And the mouse is the WRITER's while its menu is down:
    the desk's rectangle waits are not posted in a writer's wake.
  - AT A POLL THAT IS NO IDLE (`aes_switch.scheduled(..., at_polls={poll: interrupt})`). idle polls the keyboard
    EVERY time round its loop — with a process woken or ready too — so an interrupt that arrives between two
    processes' turns is taken THERE. A key that arrives one poll after the press (its forks run, the screen manager
    woken and not yet moved to the ready list) wakes the desk BEHIND the manager: the manager writes first and the
    desk answers A KEY AND A MESSAGE IN ONE WAKE ($11) — a wake no delivery at an idle makes. A poll is named by its
    ordinal among the run's polls (idles among them), held on every shore like an idle (below), and its delivery is
    checked against the three words idle tests (`aes_switch.what_idle_tests`): where in its loop the dispatcher
    polled. ("No real run reaches $11" stood here, pinned by a passing test, until the wave's review: it was true
    of the idles the driver delivered at, and of nothing else. `docs/agent-playbook.md` has the lesson.)
  - WHAT NO RETURNING RUN WAKES IS A CLASS HELD BY A SWEEP (`aes_evlib.NOT_WOKEN`, `what_wakes`;
    `test_aes_evlib_woken.py`). A blocked arrival with no woken counterpart must say why — a rectangle no mouse can
    enter, a negative time, a pipe whose other end is the waiter, a lock whose holder a harness call parked — and
    the one delivery its entry names proves little: a hand-picked "tried" can be an event that could never have
    satisfied the wait (the screen manager's wait to ENTER a rectangle stood in that table, tried with a move OUT
    of it). So every member is swept with EVERY KIND OF INTERRUPT THERE IS (`EVERY_INTERRUPT`: a key, each button
    event, the ticks, the mouse into and out of every rectangle a scenario names, onto the bar), each alone at the
    dispatcher's first idle, on the ROM's own run: none may return in the caller. The sweep is held non-vacuous —
    over a wait of each kind an interrupt satisfies, exactly the members that bring its event wake it.
    AND WITH EVERY CHAIN (`EVERY_CHAIN`, band 4 wave 3's step S): one interrupt alone at the first idle answers
    nothing for a wake that takes SEVERAL — the sweep was blind to sixteen arrivals that registered rows do wake.
    A chain is what arrives at successive idles in order, and at a poll that is no idle: the menu chain (ending in
    a CLICK — a press held on an item makes ctlmgr spin in yields and the dispatcher never idles again:
    `evlib.SPINS`, shown once), ticks at four successive idles (a delay queued behind others runs out one an idle),
    each kind of event after an opener that changes whose the mouse and the screen are (the mouse onto the bar,
    off it), and a key, a click or the ticks at the poll between two processes' turns. A chain's answer is that of
    its shortest prefix that does not leave the machine idling. `what_wakes` is both halves
    (`woken_alone_by` | `woken_in_turn_by`); `the_sweep_wakes(scenario, nth)` is the first member found, and
    `test_the_sweep_wakes_every_arrival_a_registered_wake_is_known_to_wake` holds it over EVERY woken arrival of
    `WAKES` — a sweep must find every wake the battery already knows, or its silence over NOT_WOKEN says nothing.
    WHERE ONLY ANOTHER PROCESS COULD SATISFY THE WAIT (a pipe's other end, a lock's holder: nothing to "try") the
    stated reason is a FACT OF THE ROM-MADE MACHINE, read at every arrival (`evlib.ONLY_ANOTHER_PROCESS`: the pipe
    full and the caller's own with no reader waiting; empty with no writer waiting; the lock's holder PARKED — and
    WHAT THAT HOLDER WAITS FOR — or nobody), with a RED that each is false of a machine it does not describe. A
    reason left as a sentence is held by nothing.
    "NONE RETURNED IN THE CALLER" IS NOT "NONE WAKES IT" (gate 13): the sweep has FIVE answers (`evlib.swept`:
    RETURNS, NEVER, ANOTHER_PROCESS_RETURNS, NOT_TAKEN, SPINS) and only NEVER is evidence that a member does not
    wake the wait. A run that ends IN ANOTHER PROCESS ended before the waiter could be seen woken or not — over a
    lock held by a HARNESS-PARKED process (parked for a key) a single Return un-parks the holder, whose
    continuation is the sentinel: the waiter's TAIL IS NOT RUN, which is an unpinned tail, not an unwakeable wait.
    A chain NOT_TAKEN (the run makes no such poll) says nothing. So the battery pins EVERY answer of every member
    over every NOT_WOKEN arrival (`ENDS_IN_ANOTHER_PROCESS`, `NEVER_TAKEN`), says which scenarios are of that kind
    (`THE_HOLDER_IS_HARNESS_PARKED`), and the tail they leave unrun is run over a ROM-RUN holder
    (`THE_LOCK_THE_MENU_HOLDS`: the same call against the screen manager's menu, woken by the menu let go). When a
    harness call parks a process, its continuation is the harness's: give the scenario a real holder, or say
    "unpinned" — never "cannot be woken".
  - WHAT IS HELD: each wake's events stated in a table and held to the ROM's run (`test_aes_evmulti.WAKE_CAME`),
    the same call's case AT DSPTCH beside it, the answers, the cancel, the order of the aprets (the free list's
    head), and — on the blobs — GCC's frame across savestate / switchto. Plant a trap in each arm of a tail and
    count the reds before believing a coverage figure: a figure read off an instrumented build OLDER than the
    battery it describes is not this battery's.
  - SWEEP A TAIL ON A PRIVATE BUILD AGAINST THE WAKES ALONE, host and blob as TWO runs (a tail mutant the host kills
    and no blob row kills means the target's frame across the switch is unheld). ev_multi's expressions: host `-k
    "through_the_scheduler or woken_through or after_the_wake or tail_clears or leaves_the_sent_mark or
    key_typed_with or key_polled or two_processes_woken or press_brings or woken_in_one_idle or
    through_the_menu"`, blob `-k both_blobs`.
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
  wrote). This is how every blocking arm of a wait is verified UP TO THE SWITCH — it bisects: it says which half of
  a blocking call differs. What runs after it is the wake's (below; "TIER 3: A ROW THAT SWITCHES").
- THE DISPATCH HOOK REFUSES. A twin that reaches dsptch calls `aes_dsptch` (`aes/switch.h`): off target that is
  `recreate_dispatch`, asked before any guard, whose binding in every case and every child refuses by name — "the
  call would block" or "would yield", told apart by the running process's PD_STAT as disp tells them — and prints the
  frames handed so far. A run that blocks inside a rebound entry is compared where its twin stops, AT dsptch.
- ...UNLESS A CASE SWITCHES THE MODEL ON (`test/aes_switch.py`) — THE DEFAULT IS STILL TO REFUSE.
  `aes_switch.scheduling(reference, foreign=)` binds, for its own runs alone, `recreate_dispatch` to the C scheduler
  `aes_disp` (`src/aes/evdisp.c`, host only: disp's own loop), `recreate_poll` and `recreate_idle` to the case's
  deliveries (every poll of idle is told to the first — it counts them and lays what is due at one that is no idle;
  the second is asked where the machine waits) and `recreate_process` to a nested run of the ROM. No other case of the suite is touched by it.
  - THE ROM'S SIDE is `aes_switch.scheduled(entry, frame, machine, {idle: interrupt})`: ONE run through the ROM's own
    dispatcher. An IDLE is idle's poll reached with nothing ready, nothing woken and nothing queued
    (`AES_ROM_IDLE_LOOP`) — where the machine waits for an interrupt — numbered as the run makes them; a delivery is
    taken there exactly as `interrupted` takes one at a door call. EVERY arrival at that place is a POLL, numbered
    too: `at_polls` names one that is no idle (above), and one named at a poll that IS an idle, or that the run
    never makes, is refused by name. An idle with nothing due is passed; a second in a
    row after the last delivery ends the run. A run that reaches its return in ANOTHER process is refused.
  - THE C'S SIDE is `aes_switch.modelled(symbol, typed, machine, reference, foreign=)`, in a fork: the process the
    scheduler comes back to is the caller → the C's call RETURNS; the idle hook lays the reference's deliveries at the
    same ordinals (and refuses an idle the ROM's run did not make: "the call would block"); a FOREIGN process is the
    ROM's own code from switchto until the ROM's disp is about to enter the caller again. ONE READING of a run's three
    stops (`dispatcher_stop`), whoever drives the run.
  - COMPARED (`held_to_the_scheduled_run`): the return, the idle count, the answer, the whole image — outside the
    caller's saved context, the dispatcher's stack, `$8994` and the event layer's own drops, each only where the ROM's
    run stored it. (That is the HOST's model, which stores no SR. At Tier 3 the dispatcher's save word `$8994` is
    COMPARED, both bytes — all of it but the X flag on a row that declares it: `aes_switching.THE_X_FLAG_ALONE`.)
  - WHAT MAY NOT BE A FOREIGN PROCESS: one parked by a harness call (`aes_event.parked`) — its continuation is the
    run's sentinel. The snapshot's own screen manager is real. A scheduled run that idles for ever after its
    deliveries is not kept.
  - A HOOK CALLED WHILE NO PASS IS OPEN FAILS ITS TEST AT TEARDOWN (band 5 wave 1). Such a call is no case's: it is
    answered 0 and written to `refused` — which the NEXT case's `staged()` clears unread, so a candidate that called
    through a door its case never bound (a switch that handed sh_find a routine it must not have) passed. Every
    such call is now also kept in `address_hook.OUTSIDE_A_PASS` by the pointer's symbol and its key, and an autouse
    fixture (`conftest.py`) fails the test that made it, by name; a test of the mechanism itself names itself in
    its module's `CALLS_OUTSIDE_A_PASS_ON_PURPOSE`. The cure in a battery is to BIND the door, with an empty table
    where the routine must call nothing (`aes.alcyon_object_hook({})`: refused by name, inside the pass). WHO
    READS THE RECORD: pytest's own process alone (`address_hook.read_by_this_process`, declared by `conftest.py`)
    — at a test's teardown, and at its SETUP, where a record already there was made before the test (at import
    or collection, in a module's or the session's fixture) and is that test's error, never cleared unread. IN
    EVERY OTHER PROCESS — a fork left serving the hook (the guard's fork made at the call, a model's), a fresh
    interpreter (a door user's child) — nobody would read it, so the call ENDS THE PROCESS AT ONCE, by name on
    its stderr with a status of its own (`OUTSIDE_A_PASS_STATUS`), which each child road's parent already reads
    as its case's failure; a fork that serves no hook (the zygote's, `core_in_a_fork`'s without one) never
    reaches the recorder — every hook is a refuser there (`FORK_REACHED_A_HOOK`). At once, not at the child's
    exit: a child has many exits (a halt at the dispatcher's hook, an abort, a refuser's `_exit`).
  - WHAT A HOOK RAISES IS ITS CASE'S OUTCOME, WHATEVER IT IS. ctypes prints and DROPS what a callback raises.
    `AddressHook._dispatch` (`test/address_hook.py`) records it and answers a refused call; `staged()` then gives
    the case its outcome (`as_the_case_s_outcome`): a FAILURE carrying the exception's TYPE, words and traceback,
    chained to it (a bare `assert`, a KeyError, a `pytest.fail` — a `BaseException` that is no `Exception` — each
    read as what it was, not as "raised: " with nothing after the colon); `pytest.skip` is a SKIP; and a
    KeyboardInterrupt or a SystemExit — which could not cross the callback — IS RAISED AGAIN, ITSELF, as the binding
    closes, whatever the run then failed by: the session stops as it was asked to. The door's seam keeps an effect's
    words when the run fails too, whatever it raised (`event_hook`). ONE MECHANISM, whoever binds the pointer
    (`address_hook.answered_or_recorded`, `raise_what_stops_the_session`, `as_the_case_s_outcome`): the scheduler's
    hooks (`aes_switch.Scheduling`) answer REFUSED through it, say the raise by name on stderr (a fork's only
    voice) and give it the same outcome as their binding closes. A hook written outside it owes the same — THE DOOR
    CHILD'S DISPATCHER HOOK UNDER THE MODEL DID NOT (the read of the host slots raising at a dispatch was printed
    by ctypes and dropped: the twin ran on and the child exited 0): what that child's own Python raises at the
    dispatcher now ends it by name with the harness's own
    status (`FORK_RAISED`), and a door user's modelled run says how many times its process was parked
    (`Modelled.parked`): an audit that read nothing is no audit passed.
  - ITS LEAF HOOKS (`aes_switch.IDLE_HOOKS`) ARE THE WORKER'S FORKS, not the zygote's: a named hook must live in a
    module the zygote holds (below), and it holds no battery's helper.
- SR SAVE WORDS, AND THE LEDGER RULE. The words a bracket parks (`sr_mask_saving` / `sr_restore_from`, `aes_spl7_save`
  / `aes_spl_restore`: nothing stored off target, the ROM's two instructions on it) are each a NAMED drop out of ONE
  table, `aes_event.SR_DROPS` `{save word: why}` (psetup's `$8998`, spl7's `$8996`); `sr_drops(*words)` makes a
  case's `dropped_windows`. A WORD IS DROPPED ONLY WHERE THE ROM'S RUN STORED IT, at every place two shores are
  compared, by one rule (`aes_event.not_compared_where_the_rom_stored`: the ROM's memory as compared against what
  its run started with) — no SR byte is left out unconditionally, so no battery lists which routines reach a
  bracket, and a C that writes a save word the ROM's run left alone is red. AT TIER 3 THE DROP IS SYMMETRIC: a row
  that drops a save word is held to OUR run's ledger having stored it too (`tier3.vet_what_our_run_stored`, the
  rule's ONE home — `measure` holds that it RAN, on every measuring path; a transcription row reads no drop)
  — a build whose mask bracket was lost would otherwise hide behind the drop; it is what pins a bracket's PRESENCE
  on target, which no host battery can (the host stores no SR). The dispatcher's own (`$8994`) is stored after
  dsptch, where no host core goes but the model's: it is STAGED at the value the ROM's run leaves and, at Tier 3,
  COMPARED on every row that switches — savestate and switchto are the ROM's instructions in both builds — whole,
  but for its X FLAG (`$10` of `$8995`) on the rows that DECLARE it (two today: band 5 wave 1). A door user
  drops an SR word where the ROM's run stored it (`DOOR_RUN_DROPS`) and an interrupted row settles it, both by
  derivation — no row names such a drop by hand. (Unexercised: no door row's ROM run stores one, measured before
  and after flip 3.)
- A DROP IS SYMMETRIC, WHATEVER ITS KIND: every dropped byte but the Line-F mask word is one OUR run stored too
  (`tier3.drops_held_to_our_run`; measured over 688 dropping rows: every other kind is stored by our run) — an SR save
  word, the dispatcher's stack, a saved context's D1/D2. A build that lost the store cannot hide behind the drop. And
  "a dropped row has a companion that drops nothing" admits exactly the VETTED by-nature longwords: a freed EVB's QPB
  address (below) and a relocated code pointer.
- A CODE ADDRESS IN COMPARED RAM IS RELOCATED, NEVER DROPPED (`bench/tier3.py`: `RomBench._call`, `fork_relocation`).
  Three places hold one: THE FORK QUEUE's 32 code slots (`aes_event.FORK_CODE_SLOTS`, defined once) — a fork
  function's address is the ROM's in the ROM and `aes_<fn>_fork`'s entry in our build; THE RECORDS OF A RECORDING
  (appl_trecord's buffer, back from the cursor while a record's code is a fork function's: forker's recorder copies an
  entry code and all and merges ticks by comparing code addresses); and THE SIX LONGWORDS THAT CAN HOLD A GLUE'S
  ADDRESS (`aes_event.GLUE_CODE_SLOTS`: the VDI's two vectors, the AES's contrl[7..8] and [9..10], its two save
  longwords). ONE REGISTRY DECLARES THEM, beside the slots (`aes_event.CODE_RELOCATIONS`: what, the slots, our entry
  for each ROM routine, mapped at a run's entry or at its exit alone), and ONE READING serves every site that maps a
  code address (`tier3.code_relocations`: a run's entry and exit, a delivery, a slice's mark) — no table fetched from
  a battery by its name with a silent default. AN ENTRY DECLARED BESIDE THE TUPLE IS NAMED
  (`aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3`: what, why, the slice that owes its site — today the screen
  manager's entry, `SCREEN_MANAGER_ENTRY`, read by the takeover alone until the flip): every `RelocatedCode` is in the
  tuple or in that list, and the list must be EMPTY once a Tier 3 row runs on a takeover machine
  (`test_aes_boot.py`). The queue and the recording are mapped ROM → ours as a machine or an
  interrupt's delivery is laid into our blob and back before the kit compares; THE GLUE IS MAPPED AT EXIT ONLY — a
  row's machine holds the ROM's glue in the vectors, and a vex call hands what it DISPLACED to wherever its caller's
  contrl lies (a displaced value travels: mapped at entry, vex_butv's row differs at its caller's own contrl).
  THE ROUTINE THAT DRAWS NOTHING IS OF THIS KIND TOO (justretf; `aes_event.HANDED_ENTRY_SYMBOLS`, band 4 wave 3's
  step T): a playback hands it to the VDI twice (ap_tplay's vex_curv and vex_motv) and gets it back, displaced, in
  contrl[9..10] where appl_tplay returns — the ROM's `$fed424` there on the ROM's shore, `aes_rom_justretf` on a
  blob, red in exactly that longword without the mapping. It is in the registry's entry (`GLUE_CODES.symbols`),
  NOT in `GLUE_ENTRY_SYMBOLS`, which stays the two glues the dispatcher's and the interrupts' batteries hold it to.
  Nothing is dropped, the compare is exact, and a build that queued or installed ANOTHER function's entry maps back
  to the wrong ROM address and differs. AND A RELOCATION THE BUILD LEFT UN-APPLIED IS REFUSED BY NAME
  (`tier3.vet_no_slot_names_the_rom`): the back-map rewrites only OUR entries, so a slot our run stored THE ROM'S OWN
  address in (the host arm of `fork_bchange()` compiled into the blob) equalled the ROM's memory and passed — 26 of
  26 rows green, a queue our forker would `jsr` into the ROM from. After our run no slot of the registry holds a ROM
  address of it unless the run CAME WITH it: an argument the call was handed (forkq's code, gsx_setmb's routines)
  or, for the glue, what its slots held at entry. (What that leaves — an installer storing the ROM's glue over a
  machine that already holds it — is held off the vectors: `test_aes_irq.py`.) Off for a routine whose run still reaches the ROM's own forker (a
  `jsr` into the ROM's ev_multi), which must find the ROM's addresses. THE HOST STORES THE ROM'S ADDRESSES
  (`ALCYON_ROUTINE(rom, ours)`: Tier 1 stays exact); the target its own.
- ONE SETTLING, ONE REGISTRAR. `aes_event.settled_in_windows(machine, writes, staged, dropped=None)` is the one
  spelling of "a priced row's bytes that differ by nature": every byte of the windows `staged` that the ROM's run
  STORED is staged at the value the run leaves (the row's companion then compares it with nothing dropped), and the
  windows `dropped` — those staged, unless a row drops fewer — are cut to the bytes the run stored: the row's named
  Tier 3 drops. `settled_where_stored` is its case for WORDS (the mask word, an SR save word); `settled(name,
  arguments, machine, polls=)` makes the ROM run and settles every word that differs by nature, `savptr` moved into
  the stack band where the run takes the BIOS trap; a switching row settles WINDOWS (the caller's saved context, the
  dispatcher's stack) and drops fewer than it stages (the SR save words are staged and compared: our build stores them
  as the ROM does). `aes_event.register_row` is the one registrar of a leaf row of the event layer: the waits'
  (`aes_evlib.register`), the input's (`aes_evinput.register`, which tells it the two routines that POLL), the
  processes-and-pipes' (`aes_pdpipe.register`) and ev_multi's own (`aes_evmulti.register`) all end on it — and a DOOR
  USER's row (`aes_event.register`) is settled by the same spelling (`settled_where_stored` over every word that
  differs by nature). WHAT A ROW SETTLES BEYOND THE TWO WORDS EVERY LAYER HAS IS PINNED, a census per layer
  (`test_aes_event.BY_NATURE_CENSUS`, held to an independent spelling of the settling; the door users'
  `test_tier3.DOOR_USERS_CENSUS`, read off the registry — none today): a row newly under a bracket, a trap or a QPB
  reds until it is written in. A WORD IS SETTLED WHOLE OR REFUSED: a run that stored
  one byte of a word that differs by nature did something its drop's reason does not name (`settled_where_stored`
  refuses it by name — a finding to rule on, never staged and dropped in silence). Held:
  `test_every_row_a_layer_registers_is_staged_and_dropped_as_the_rom_s_own_run_says` — against AN INDEPENDENT
  SPELLING (the oracle's own run of each row, not the kept derivation the registrar reads: a registry compared with
  the function its registrar calls holds "no layer bypasses it" and nothing of what it stages) and against THE
  CENSUS (`BY_NATURE_CENSUS`): the registrar settles whatever a row's ROM run stores, with no ruling, so the rows
  that use a WIDER kind — psetup's or the dispatcher's bracket, a QPB's address, `savptr` moved by the run alone —
  are pinned by routine and a new one reds until it is written in with its reason. (The door users' rows and
  ev_multi's own are not in it yet.) A layer that writes a settling of its own is refused in review — five had
  grown.
- ONE LONGWORD A PARKED PIPE WAIT DIFFERS IN BY NATURE — THE PARKED QPB, FOUND ON THE MACHINE. aqueue keeps a pipe
  wait's QPB by its ADDRESS in the EVB it queues, and that QPB lies in its caller's stack on each shore: ap_rdwr's is
  its own argument frame, ev_multi's a local of its own frame (the twins': a host slot per process, below). WHO PARKS
  ONE IS READ OFF THE MACHINE, no routine named (`aes_event.parked_qpbs`): every EVB of the running process queued on
  a pipe's end whose parameter is a stack address — not "the newest EVB": a blocked ev_multi's pipe wait is followed
  by its timer's. Where the wait PARKS that EVB_PARM is dropped BY NAME and VETTED pairwise (`parked_where_blocked` /
  `parked_qpb_drop`): the same EVBs on both shores, each shore's longword an address in ITS stack band naming the same
  eight bytes (process, count, buffer) — and, off target, OUR address must be THE host slot of the entry's own role
  and the running process (`our_qpb_slots`: a twin that parked another process's slot, or another routine's, is
  refused). AND AT A RETURN: a wait cancelled or answered is freed AS IT IS, the frame's address still in EVB_PARM —
  the same by-nature longword in a FREE EVB, found by the ROM run's ledger (`qpb_addresses_kept`: an EVB_PARM the run
  STORED whose value is a stack-band address), dropped and vetted the same way. A wait the MACHINE came with holds one
  address on both shores and is COMPARED (its bytes are not vetted there: a staged machine carries no stack band).
  Used by the leaf batteries, a door user blocked inside a rebound entry (held too to what the entry's row says it
  parks, `Entry.parks`), and `register_row`. Never a window.
- A HOST SLOT PER PROCESS. A frame local that stays live while its process is BLOCKED — its routine reached the
  dispatcher with the local's address parked in a record another process reads — is live in two processes at once:
  ap_rdwr's QPB, which a parked pipe wait's EVB points into until the other end serves it through that address. In
  the ROM each is on its own process's stack. Off target such a role is `HOST_PROCESSES` frames
  (`host_slot_claim_for(ROLE, local, process)` / `host_slot_release_for`, `include/host_slot.h`), the RUNNING
  process's id choosing one: an address the IMAGE decides, the same in whichever host run laid the frame (a "next
  free slot" would collide across runs — a parked frame is laid in one run and read in another). On target the
  macro is the local's own address and `process` is not evaluated. ev_multi's QPB is a second such role
  (`HOST_SLOT_AES_EV_MULTI_QPB`), claimed on its blocking arm only and given back at the return (held by a test
  that makes two calls in one fork). THE SCREEN MANAGER'S HANDLERS' OWN FRAMES ARE THREE MORE, per process from the
  day they landed (band 5 wave 1): the rectangle a window's drag is held by and the two words it answers into
  (`HOST_SLOT_AES_HCTL_WINDOW_DRAG_RECT` / `_DRAG_ANSWERS`), and mn_do's two answers under hctl_rect
  (`HOST_SLOT_AES_HCTL_RECT_CHOICE`) — COMPACTED, not the ROM's frame: no gap of the band holds nine frames of
  hctl_window's 36 bytes, so what is read before any wait (the window's rectangle, the elevator's corner) has plain
  slots given back at once. Every OTHER slot a routine holds across a wait owes this shape the moment two C
  processes can be inside one routine — band 5. Wave 3's AUDIT names them
  (`test_aes_event.SLOTS_HELD_WHERE_PARKED`): one frame for every process today, and sound, since a process other
  than the caller is the ROM's own code on the host.
- TIER 3: THE ARRIVALS RULE. Both runs still arrive at a rebound entry — the same ordinal, delivery, slice mark and
  frame — but it opens NO window: the ROM routine's cycles stay the ROM's own, the twin's are ours, and the table's
  sub-line counts "N call(s) of a rebound entry in the own cycles". A twin that runs an AES ROM cycle is refused by
  name (rebind the entry it called first). So a flip MOVES every row that reaches the entry: save the table before
  and after, list every moved row, and hold that no other moved. A row stops opening a window by derivation when
  its function's last `jsr` into the AES text is gone (none is left: every entry is rebound). NO WINDOW OPENS AT A REBOUND ENTRY ON EITHER SHORE, however it
  is reached: the ROM's watch reads the rebound set off the build, not off the static call graph (which holds no
  edge through a queued fork function's code — the ROM's bchange reaching post_button under the ROM's forker).
- TIER 3: A ROW THAT CALLS A REBOUND ENTRY IS HELD ON TWO COUNTS. With no window, the row is a differential of the
  whole call and the CALLER's body could hide in the entry's cost (gr_stilldn is 340 cycles of its own round an
  ev_multi of 5,374). So every such row — and every uncovered stretch of a session — is held ≤ the bar twice, both by
  derivation: **own**, the ratio column (every own cycle of ours against the ROM's, the rebound entries' calls in
  both), and **the caller's own**, each shore's own cycles NET of what the rebound entries' calls cost it (the twins'
  blob cycles on ours, the ROM routines' AES-span cycles on the original's: `DoorWindows.own_inside`). HOW TO READ A
  ROW THAT SHOWS BOTH — the line under it: "whole run: W — own A cycles against the ROM's B …; the OS both run X
  against X, N call(s) of a rebound entry in the own cycles — the caller's own, net of them: C against D, R.RR, and T
  in thunks: G with them". W is everything, the OS included; A / B is the ratio column; C / D = R.RR is the second
  count; G counts the thunks back. A second count ABOVE the first says the caller's body is the dearer part and the
  twin the cheaper (bchange's press on the bar: 0.87 and 1.01); BELOW it, the reverse.
  THE SECOND COUNT HAS A LINE OF ITS OWN, AND ITS OWN THUNKS: `TWO COUNTS: 0.45 / 0.37 (812 against 2216) — own / the
  caller's own, net of N call(s) of a rebound entry; T of the row's G thunk cycles are the caller's own: R.RR with
  them`. Which side of a call a thunk ran on is MEASURED, call by call (`DoorWindows.glue_inside`): a thunk inside
  a rebound entry's call is the ENTRY's (its twin's road to a transcribed core), every other one the caller's, and
  counted back onto the caller's count — over the bar with them and under it without, the row is `glue` on the
  second count as a (V) row is on its first. A PINNED row that calls a rebound entry is pinned on both
  (`tier3.CALLER_PINS`: DRIFTED on either, and with no second pin at all). STATUS QUOTES THE PAIR IN THE LINE'S OWN
  FORM — `0.45 / 0.37 (812 against 2216)` — wherever the two differ by more than 0.05, and `test_status.py` PINS
  IT BOTH WAYS: every pair the ledger quotes is one the table printed for that address, every pair that differs is
  quoted, and the section's "N rows carry both; they differ … in M" is the table's count. Never typed by hand: re-quote
  from `make bench`. The ratio cells of the rows are the first count's. The RED:
  `test_a_delayed_body_through_the_door_reds_its_row…` asserts WHICH count catches a body made dearer, and
  `test_a_row_round_a_rebound_entry_is_held_on_both_counts` reds each count alone.
- TIER 3: THE GENERAL GUARD — NO ROW'S RUN OF OURS SPENDS A CYCLE IN THE AES'S ROM OUTSIDE ITS DECLARED WINDOWS
  (`tier3.vet_our_run_kept_out_of_the_aes`, in `measure`: `RomBench._call` profiles every row's own run). It is what
  (V) held for `net` rows alone: a plain C row could run the AES's ROM through a CODE POINTER IN DATA — forker over a
  ROM-made queue with the relocation off spent 61,120 cycles there and was "equal" at 1.00 — and be priced. Sliced
  rows are not asked (a slice is cut from a whole run that the ARRIVALS rule holds call by call); a case that hands `measure` the
  KIT's own bench is not this guard's. TO DECLARE AN ENTERED-BY-THE-MACHINE'S-POINTER EXCEPTION — a row whose run must
  enter ROM text because the MACHINE holds the ROM's address and the row cannot relocate it (a transcription row is
  held to the whole register file) — add it to `tier3.ENTERED_BY_THE_MACHINE_S_POINTER` with the EXACT cycles it
  spends there and the reason: the guard holds it to that number, not to "some". ONE stands: drawrat's bare-`rts` `.S`
  row, 16 cycles in the ROM's justretf (the snapshot's `$947a`). Prefer a relocation; a declaration is for what cannot
  be relocated.
- TIER 3: OUR OWN DISPATCHER IS WATCHED (`aes_event.DoorStops(dispatchers=)`, `tier3.our_dispatchers`): inside a door
  call the watch stops at OUR blob's `aes_dsptch` as at the ROM's, so a twin that blocks where the ROM returns is
  refused BY NAME in one stop — it used to idle in our dispatcher for 16,000,000 instructions and end in the oracle's
  RuntimeError, which no strict sweep counts a kill.

- TIER 3: A ROW THAT SWITCHES (`test/aes_switching.py`; band 4 wave 3 — 108 rows of the table). A call that BLOCKS
  AND IS WOKEN leaves by the dispatcher and comes back by it — ONE RETURNING RUN on both shores: the ROM's routine through the
  ROM's dispatcher, our twin through OUR dsptch, disp, savestate and switchto round the C of forker and idle. Such a
  row says so in its NINTH FIELD: an `aes_event.Switches` where a door row has `{door call: (found, wrote)}` — the
  deliveries at the dispatcher's IDLES (`{idle: (found, wrote)}`, as `aes_switch.scheduled` takes them), how many
  idles the ROM's own run makes, the PD that makes the call, and the row's door-call deliveries if it has any. It is
  neither a dict nor a tuple (indexed by a door call's ordinal it raises), and true with nothing delivered: read it
  through `aes_event.switching(delivered)` / `at_door_calls(delivered)`. EVERY RUN OF THE ROW IS WATCHED AT THE
  DISPATCHER (`aes_switching.Switching`, one class for both shores — `aes_event.delivering` answers it for the
  sweeps' replays and Tier 3's originals, `tier3` builds ours):
  - AN IDLE is idle's poll reached with nothing ready, nothing woken, nothing queued: the ROM's at
    `AES_ROM_IDLE_LOOP`, ours where `aes_idle` calls `aes_chkkbd` (ev_multi polls too: the return address under SP
    tells them apart). The delivery of that ordinal is checked against the memory it lands on and laid, at no cost;
    a run that idles ONCE MORE than the ROM's did is refused there by name (it used to be the oracle's budget), and
    one that made fewer is refused as it ends (`vet_ended`).
  - A POLL is every arrival at that same place, an idle or not (`Switches.at_polls`, `Switches.polls`): numbered as
    the run makes them on either shore, the row's delivery of a poll's ordinal checked and laid there as an idle's
    is — and checked against which process stands ready, which woken and how many forks are queued, as the ROM's
    run held them (a dispatcher that polled at another point of its loop is refused where the delivery would land:
    the same key, the same final image, another order). A run that polls more or fewer times than the ROM's is
    refused as it ends; a delivery named at a poll the run never makes is refused where the watch is made.
  - EVERY PROCESS ENTERED IS FOLLOWED at switchto's `rte` — the ROM's bytes in both builds: the same offset — to
    the instruction it resumes at. THE DOOR WATCH IS THE ROW'S OWN PROCESS'S (`DoorWindows(blocks=False)`, the
    watch's `inner`): a door call that reaches the dispatcher STAYS OPEN ACROSS A SELF-RESUME and closes when its
    process is resumed, its cost — the switch in it — in both own columns, the row held on TWO COUNTS as any door
    user's (measured: wind_update handing the lock over inside unsync's call, 0.64 / 0.32; ev_keybd round ev_block's
    twin, woken by a key). A DOOR CALL OPEN ACROSS A FOREIGN WINDOW IS PRICED NET OF THE WINDOW (band 4 wave 3; the
    foundation refused it by name): the window sits inside the call's own cost on each shore, so it comes off THREE
    things together, at the call's close — the call's own cost (`own_inside`), its glue, and the twin's count of
    AES-ROM cycles (`in_the_rom`: what refuses "our twin ran N cycles of the AES's own ROM"). One left in on any
    count is refused by name, a cycle of our build inside such a window is refused AT THAT CALL, and a window
    BETWEEN two door calls comes off no call (`test_tier3.py`: `test_a_door_call_open_across_a_foreign_window_…`,
    `test_a_window_left_inside_a_door_call_on_one_count_…`, `test_a_window_between_two_door_calls_comes_off_no_call`).
    Rows: mn_do with the desk's turn inside its ev_multi, ap_sendmsg with the desk's read inside its ap_rdwr.
  - A FOREIGN WINDOW is the run of another process than the row's, from its first instruction to the first of the
    row's process when a dispatcher comes back to it. The snapshot's other process is the screen manager, parked BY
    THE ROM in the ROM's ev_multi, its program (ctlmgr) not reconstructed: its saved PC, its frames and the fork
    codes it queues are the ROM's, and the dispatcher that hands the machine back is the ROM's too. So the window
    is THE ROM'S OWN CODE ON BOTH SHORES — declared, measured and held, never assumed: no door entry is a stop inside
    it; no fork may be queued at either edge (a queue entry's code is one build's forker's); `tier3` holds the two
    shores' windows equal TO THE CYCLE, whole and in the AES's text, with no cycle of our build inside, takes them
    off both own columns, and prints them under the row (`N foreign window(s): another process ran …`). It is the
    one place a run of ours may execute the AES's ROM: the general guard holds our cycles there to exactly the
    row's windows. A PROVISIONAL PRICING RULE (the user may overturn it), and its reason: while the other process's
    program is the ROM's there is nothing of ours in its turn to price, and the dispatch that hands the machine
    back is THAT process's — so after a foreign turn our process is woken by the ROM's dispatcher on both shores,
    in neither column; only the dispatch that PARKS it is ours. HELD ON EVERY PATH THAT MEASURES SUCH A RUN: the
    table's (`_held_through_the_os`, which any row carrying a `Switches` or deliveries must take: refused by name
    otherwise) and a named blob's (`tier3.switching_run_on`, behind `aes_switching.measured_on`). A drop "our run
    stored too" is held to what our run stored OUTSIDE its windows.
  - THE RELOCATION REGISTRY ACROSS A WINDOW — the answer to "a ROM-made parked process holds ROM addresses": NOTHING
    OF A FOREIGN PROCESS IS RELOCATED. Its saved PC and frames are entered as they are (they are the window). A
    DELIVERY IS RELOCATED BY WHO TAKES IT: laid at OUR idle its fork codes are our entries, laid at the ROM's idle
    inside a window they stay the ROM's (relocated there, the ROM's forker `jsr`s our fork function inside the
    window: 5,112 cycles of our mchange, the image compare still green — the RED of the rule). And a code slot the
    window itself stored (the ROM's own poll queueing kchange) is excepted from "no slot names the ROM after our
    run" — that slot, while it holds that code (`Switching.foreign_codes`) — and from nothing else.
  - WHAT IS SETTLED AND DROPPED (`aes_switching.settled`, one kept derivation a row; the one settling): the Line-F
    mask word, the caller's whole saved context, the dispatcher's stack (put back on our shore, as the yield's) —
    and THE MASK BRACKET'S SAVE WORD `$8996` where the ROM's run stored it (a delay's wait and its fork function
    raise the mask in C: the word is each build's own condition codes — the row is red without the drop, and the
    drop is held to OUR ledger too). The dispatcher's own save word is staged and compared.
  - THE HOST DOES NOT SWITCH STACKS. Tier 1 of such a row is the model (`aes_switch.modelled`: the C scheduler,
    self-resume a return, a foreign process a nested run of the ROM) held to the ROM's scheduled run over the row's
    settled machine with nothing left out but the run's own stack (`aes_switching.companion`) and — vetted first — a
    QPB's address left in a freed EVB. WHERE ANOTHER PROCESS RAN it is the ROM's own code in the host's run too, and
    what that code stores where no C ever does — the dispatcher's stack and the Line-F mask word: TWO things, each
    held needed by a RED (the SR save words stood in the rule too, and no companion needed them left out: they are
    laid back and compared) — is NOT LAID BACK over the C's image (`aes_switch.STORED_BY_NO_C`): the image keeps
    there what the machine stages, which is what the ROM's whole run leaves however often the row's process is
    dispatched afterwards. (The
    foundation's rule — those bytes held to what the ROM's run holds where its disp hands the machine back — was
    exact only for a row that never dispatches again: mn_do woken twice after the desk's turn differed in 24 bytes
    of the dispatcher's stack on no fault of the C.) The switch itself, and GCC's frame across it, are the bench's
    second differential: the image, the answer, every callee-saved register back after the wake.
  - A PARKED QPB'S ADDRESS COMPOSES WITH THE REGISTRAR. A pipe wait that blocked and was woken (or cancelled) gives
    its EVB back with the QPB's address still in EVB_PARM — a place in the waiting routine's own frame, another on
    every shore. The registrar READS IT WHILE THE FRAME IS LIVE (the watch notes a QPB the first time its address is
    seen, at an idle or where a process is resumed: ev_mesag's QPB is overwritten by its own Line-F return's trap
    frame before the run ends), keeps it with the row (`Settled.qpbs`), drops the longword by name at Tier 3, and
    VETS it on every shore: the companion against the C's own slot of the entry's role (`_vetted_qpbs`), a blob's
    run against what our parked wait named (`vet_our_qpbs`: the same process, count and buffer) — AND ITS PLACE: the
    QPB lay at or above the stack pointer its process stood parked at (`vet_the_qpbs_lay_in_live_frames`, on the
    ROM's replay and on every blob's run: the right eight bytes in a POPPED frame are right until the next call).
    A wait still queued is read again where its address was seen before (the same EVB, a second wait out of the
    same frame). An address no stop saw live is refused by name; it is never staged.
  - A MACHINE A RUN LEAVES IS MADE BY THE WRITE LEDGER (`aes_switching.left_by`): every byte the run or an
    interrupt stored, at the value it holds where the run ends — NOT "the bytes that differ from the snapshot". A
    byte the run stored with the value the snapshot happened to hold is the run's all the same; kept by difference,
    it turned back into noise over another capture of the boot.
  - THE ROW'S PROCESS NEED NOT BE THE DESK: `Switches.process` is read off the machine. The screen manager's write
    to the desk's full pipe is the screen manager's row — its saved context the one dropped, the desk's turn the
    foreign window.
  - A DOOR USER THAT SWITCHES (a routine above the event layer whose wait blocks: the gr_ loops, fm_do, mn_do,
    wm_update, ap_sendmsg) is written with three calls of `aes_event`: `woken_row(label, name, arguments, machine,
    at_idle, at_calls=None, objects=, answered=)`; `blocked_then_woken(row)` → `(held, ran)` — the premise first
    (with nothing delivered at an idle the call SWITCHES: refused at its hook, its whole image the ROM's AT DSPTCH —
    where a transient store made before the block and undone after the wake would show, and nowhere later), then
    the same call taken on to its return; `register_woken(row)` — the priced row, on TWO COUNTS, its call open
    across the switch. ITS INTERRUPTS ARE OF TWO KINDS IN ONE DERIVATION (`aes_switch.scheduled(..., at_calls=)`):
    at the entry of a door call (what a loop's earlier waits take) and at an idle (what wakes a wait that
    blocked); one named at a door call the run never makes is refused. ITS TIER 1 IS A DOOR CHILD UNDER THE MODEL
    (`aes_switch.modelled(..., door=DoorUser(objects, child doors))`): the door's binding and the scheduler in one
    fork, the twin run on through the dispatcher's hook, the frames the door was handed held to the ROM's.
  - THE HOST SLOTS HELD ACROSS A WAIT ARE AUDITED (`test_aes_event.SLOTS_HELD_WHERE_PARKED`, `include/host_slot.h`):
    each frame a door user holds while its process is parked is ONE frame for every process — sound while one C
    process can be inside the routine (another process is the ROM's own code, which claims nothing) — and a call
    that returns with a slot still held is refused by name. A slot NEWLY held across a wait reds that table. WHAT
    THEY OWE IS OWED THE DAY THE HOST RUNS A SECOND PROCESS'S C (`HOST_PROCESSES` frames each, `host_slot_claim_for`,
    as the two QPBs have) — NOT the day the screen manager is C on target (band 5 wave 2): a host run holds one
    process's C, its caller's, any other the ROM's nested run, and two tests hold that (`test_aes_event.py`: the
    process hook is the ROM's switchto; a second process's C entered through it, or a single-frame slot claimed
    twice, halts by name).
  - TO ADD ONE: `aes_switching.register(label, name, arguments, machine, {idle: interrupt})` — everything else is
    derived from the ROM's own runs (`()` for a routine of no argument, `answered=False` for an arm that sets no
    D0, `at_polls=` for what arrives at a poll that is no idle); `measured_on(blob, row)` is the second differential
    on a named blob (the table prices a row on one). ONE REGISTRAR, `aes_switching.register_row(row)`: the waits'
    battery ends on it through `evlib.register_woken`, a door user through `aes_event.register_woken`, ev_multi's
    wakes directly, and a sliced session through `aes_event.register_woken_slices` (`register_row(row, under=<its
    slices' names>)`: one settling, one record under every name). AND ONE SPELLING OF WHAT A BATTERY HOLDS OF ITS ROWS (the pilots', the waits', ev_multi's and
    the door users' all call it, so none holds less than another): `aes_switching.vet_the_premise(row,
    Premise(...))` — the ROM's own run is what the row says, and the row carries its deliveries;
    `vet_on_a_blob(blob, row, premise, windows, whole)` — the second differential on each blob, its idles, polls,
    processes, windows and whole-run cycles pinned; `vet_the_table_s_price(row, Priced(own, the caller's own,
    calls, windows))` — what the table prices, THE CALLER'S OWN PINNED wherever the run calls a rebound entry (a
    second count net of a foreign window TWICE is still under the bar: a battery that pinned the first count alone
    passed it), both counts under the bar. A second count has an invariant of its own, held where it is read
    (`tier3.caller_own_cycles`, and call by call in `DoorWindows._closed`): what the calls cost is neither negative
    nor more than the run they are part of. `budget=` on a row (`SwitchingRow.budget`, through `woken_row`) is its
    own derivation budget, declared from its measured run and held both ways as any case's (A CASE'S OWN BUDGET,
    below): a whole session of the file selector needs one. NOTHING OF THE FOUNDATION'S "NOT BUILT" LIST IS LEFT:
    one derivation that takes interrupts at door calls AND at idles, a parked QPB's address in a row that switches,
    a door user under the host's model, a door call open across a foreign window (band 4 wave 3's slices, each
    above) — and A SLICED SESSION THAT SWITCHES (its step S, next).
  - A SLICED SESSION THAT SWITCHES (`aes_event.register_woken_slices(row, {label: (start, stop)})`; fs_input's two
    sessions the user is waited for in, `test_aes_fs_input_woken.py`). A session whose waits BLOCK is a row that
    switches cut into slices like any other session (A SESSION PRICED BY ITS SLICES, below) — ONE settling from the
    ROM's own run through its dispatcher, one `Registered` under every slice's name (`aes_event.session_of`), each
    slice carrying the session's `Switches`, drops and companion. The wait that blocks is a rebound entry's call
    INSIDE its slice — the block, our dispatcher's park and the wake in the slice's own cost — so the slice is held
    on two counts. WHAT MAKES IT HONEST IS THAT A SLICE'S MARKS ARE PER PROCESS (`aes_event.Marks`):
    (1) a mark is an ARRIVAL OF THE ROW'S PROCESS. None is taken inside a foreign window: the screen manager makes
    door calls and takes traps at the very PCs a slice is cut at, and one counted would shift every later ordinal
    of the row's own. The dispatcher's watch arms none of the door watch's stops there, the marks are told where a
    window opens and closes (`foreign_window_opened` / `_closed`, through `DoorStops`), and an arrival handed to
    them in between is refused by name. (2) EVERY TOTAL A MARK HOLDS IS NET OF THE WINDOWS CLOSED BEFORE IT
    (instructions and cycles too: the cap is held on the row's own run). The windows inside a slice are kept beside
    it (`foreign_inside`), printed under the row, in NEITHER column, and held the same on both shores — as many,
    the same cycles, none of our build's; marks on either side of a window on the two shores are two slices and
    are refused (`vet_the_marks_agree`). (3) THE MEMORY AT A MARK IS COMPARED OUTSIDE THE ROW'S DROPS AND THE
    DISPATCHER'S STACK WHOLE (`tier3._differing_at_a_mark`): our dispatcher's frames lie there from the first
    switch on, deeper than the ROM's, and our image is given back over them only as the run ENDS. Each rule has its
    RED in the battery (marks deaf to a window price the lock's slice at 0.19 where it is 0.66). A `Timeline` — the
    ROM-only derivation a battery cuts its session by — is of a run that switches nowhere and refuses a window by
    name. A sliced row whose run arrives at no door entry has no marks and is refused where it would be measured.
    TO WRITE ONE: `aes_fs_sessions.Woken(at_waits, at_idles, same, budget, running)` — what the user has done by
    each wait's entry, what is done WHILE THE SELECTOR WAITS (at the dispatcher's idles), and THE SAME USER NEVER
    WAITED FOR, the returning session whose script answers its GEMDOS calls. That reuse is a premise, so it is
    HELD: the woken run makes exactly the script's calls, to its last, EACH HANDED THE FRAME THE SCRIPT'S ANSWER WAS
    GIVEN TO (`vet_its_gemdos_calls`; `Script.frames` — function numbers alone pass a selector that searched another
    path and was answered as if it had not), and — over `same`'s own machine — ends as that session ends
    (`vet_it_ends_as_never_waited_for`); each has a RED. THE END-STATE PROPERTY IS CLAIMED ONLY FOR `running is
    None`: a session over another machine (`running=`) is refused the question, and what it differs by is pinned as
    the stated difference instead (the menu's session: the mouse — the cursor's pixels and `gl_mouse_shown`). `running=` is another ROM-made machine whose
    running process makes the call (the screen's lock held by the screen manager's menu:
    `aes_evlib.the_manager_s_menu_holds_the_lock`).
  - A ROUTINE EVERY ARM OF WHICH LEAVES BY THE DISPATCHER HAS NO OTHER KIND OF ROW (the event tape,
    `src/aes/aptape.c`, band 4 wave 3's step T: ap_trecd sleeps until forker's recorder stops, ap_tplay yields before
    its first record and after each). What that taught: (1) EVERY CASE IS A `SwitchingRow` — register the ones worth
    pricing (`aes_switching.register_row`), keep the rest Tier 1 with the reason each is not a row (another count
    of a priced one; the labelled argument class; what a blob cannot run). `answered=False` for the one that sets
    no D0; AT DSPTCH `switches=YIELDS` for a bare yield, `BLOCKS` for a sleep. (2) THE MACHINES ARE ROM RUNS'
    (`aes_switching.left_by`): a playback's machine is what the ROM's own ap_trecd LEFT, real interrupts taken at
    its dispatcher's idles — nothing of a recording is typed by hand but the one labelled class of records no
    recording holds. (3) A BARE YIELD INTO ANOTHER PROCESS needs nothing new: the foreign window opens at that
    process's first instruction after our switchto's `rte`, as after any wait's. (4) WHAT NO RUN OF A BENCH CAN SEE
    IS READ OFF THE BUILD'S OWN INSTRUCTIONS (`test_aes_evfork_interrupted.blob_body(blob, symbol)`, both blobs): a
    bench run is entered at IPL 7 and takes no interrupt the watch does not lay, so ap_trecd arming the recorder
    UNMASKED leaves every image and ledger as they are; and two stores both made before the next compare (the
    cursor routine exchanged before the motion routine) have no order in any image. Sweep first, then write the
    instruction pin for the mutant that survives — that is how the second was found; and PIN THE STORES, NOT THE
    NAMES: the first pin held every instruction that NAMES the recorder's count or cursor inside a bracket, and the
    flag armed before the mask was raised stayed green (gate 13) — it now holds every STORE to the three words,
    inside a bracket and in the ROM's order. (5) A LIMIT OF THE MIXTURE,
    HELD AS A REFUSAL: a recording with another process's turn INSIDE it is red on a blob in the records made
    inside the foreign window (the ROM's forker ran those events and recorded the ROM's fork-function addresses;
    ours numbers them 0) — Tier 1 only, the refusal pinned by name so it is not met by surprise. (6) A ROM
    BEHAVIOUR THAT IS A FAULT IN A RUNTIME HELPER IS REFUSED BY NAME, NOT ANSWERED: a scale of 0 is ldiv's divide
    by zero, which the ROM survives through vector 5's `rte`; the C halts where ldiv's core does. (7) "UNREACHABLE"
    IS A CLAIM ABOUT THE ROM, NOT ABOUT THE BATTERY'S BUFFER: "more than 4,095 records cannot be recorded" was true
    of the 64-byte band the recordings share and false of the machine (a count of 0 records until
    Control-backslash; any free RAM is a buffer) — two mutants argued equivalent on it answer `$100e` for the ROM's
    `$f00e`. A long ROM run is a Tier 1 row with a DECLARED BUDGET (`SwitchingRow.budget`), not a reason to argue.
  - `test_status.py` HOLDS THE LEDGER TO THE REGISTRY BY NAME: each routine's count of rows that switch, the three
    sentences that count them all, AND WHICH rows — its verified row lists them after `THE ROWS THAT SWITCH:` in
    the Tier 3 cell, each `**ratio** <the table's name> (`net`…)` (or `THE ROWS THAT SWITCH (each the table's
    `<prefix>…`):` where every name opens with the same words, said once), both ways. A paraphrase is red: write the
    name as `make bench` prints it. (It found four of ev_block's so paraphrased the day it landed.) SINCE GATE 13
    THE LIST IS HELD AS A LIST: no name twice and as many as the Cases cell counts (two SETS of names forgave a row
    listed twice in place of another); the ratio before each name is THAT ROW'S in the table — `**0.66 / 0.32**`
    its two counts — not merely one "measured for the address"; and an address has ONE verified row (a second was
    read over the first). Each with a RED on a made ledger
    (`test_a_wrong_list_of_the_rows_that_switch_is_refused_each_way`).
    AND THE OTHER PRESENT-TENSE COUNTS ARE HELD, each in a fixed form: the Components cell's
    `THROUGH INTERRUPTS (N, lo–hi — M of them SLICES of K sessions` (it said 55 over a registry of 56), a Cases
    cell's `N rows (… M SLICES of K session(s)`, the two counts' `(N on the unrounded cycles), the caller's own is
    the HIGHER in N, and N are over 1.00`, and `THE TABLE TODAY: a FOREIGN WINDOW in N of its rows; the save word
    `$8996` dropped by name in M of the rows that switch`. A count the ledger states in the present tense and
    nothing derives is deleted or held — the wave logs quote history and are left alone.

INTERRUPTS AT A DOOR ENTRY. A loop like mn_do or gr_dragbox only leaves its later states when the mouse or button changes
WHILE it runs. `aes_event.interrupted(name, arguments, machine, {k: effect})` delivers that change on both sides. The ROM's
watched run is stopped at the k-th door entry. The ROM's OWN interrupt code (the VDI mouse ISR and the tick glue: `press`,
`release`, `move_to`) then runs over a copy of the memory at that point, with its stack frames left out. The bytes it wrote
are laid in at that same entry. The C, in a child, gets the identical bytes at the same ordinal before its twin runs.

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
- `budget=B` (on `interrupted`, `register_interrupted`, `register_slices`, `run_event`,
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
  calls, glue); the reset overhead comes off a slice that starts at `ENTRY` only. Every vet of a door row and the
  bench's second differential still run over the whole session.
- MEMORY IS COMPARED AT THE MARKS: our run must reach the slice's start after the same door calls as the ROM's and with
  the same memory (outside the stack band, the blob and the row's drops), and the same again at its stop — else the
  ratio would be of two different computations. Refused by name: a slice started one call late, "diverged before the
  slice's start", "diverged inside the slice", an end never reached, a slice that runs backwards, a session that
  blocks or has nothing delivered. `ENTRY` and `RETURN` carry no memory of their own (the whole run's differential).
- EACH SLICE IS UNDER `SLICE_INSNS` (200,000) on the ROM's own run of it; one over it is refused, to be cut finer.
- Measure before registering: `aes_event.rom_timeline(name, arguments, machine, delivered, traps=(handler, …),
  budget=)` lists every door call and listed trap with what the ROM had spent there; `slice_cost` prices one cut.
- A sliced session is taken through interrupts AT ITS WAITS (keys typed ahead leave no waits to cut at), and cannot be
  `psg_seed` / `schedule` / `regs` seeded. A session whose waits BLOCK — the user acts while the selector waits —
  is sliced through `register_woken_slices`, its marks per process (TIER 3: A ROW THAT SWITCHES, above).
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
sees a screen already given back); every VDI CALL in order (opcode, intin, ptsin) — THE WHOLE SESSION'S LEDGER on both
shores: every `trap #2` of the ROM's run, those INSIDE its door calls of rebound entries too (`aes_fslib.VdiCalls`),
against every VDI function a door binding serves on ours, the event layer's own among them (chkkbd's three polls,
mchange's vq_mouse: `aes_event.door_vdi_functions`), in process and in a child — never "count nothing while a twin
runs", which would leave the event layer's VDI calls held by no ledger; and WHAT THE ROUTINE HOLDS as each
VDI call is made (`aes_fslib.held_in`: its tree, its texts, its scratches, hashed into the ledger on both shores), which
is what sees a word set and put back between two waits.

The dispatcher refuses in two ways, matched by `aes_event.BLOCKS` and `YIELDS` (the dispatcher's own words). A call that
WOULD BLOCK leaves its process waiting. A call that WOULD YIELD keeps the caller ready but switches: unsync handing the lock to
a queued waiter does this. The core's generic halt line names both, so a bare "would block" substring passed a yield as a
block. `interrupted(..., {}, switches=)` — a case that ends blocked, `blocked_then_woken`'s first half — compares the child's
whole image with the ROM's where the call reaches the dispatcher.

THE C RUNS FIRST IN A CHILD. A core of the event layer that goes wrong does not fail an assertion: a door user loops
where the ROM's run ends, a list routine walks a list that no longer ends or stores through a link that is no address
(the host's refusal: an abort), a wrapper and a hook disagree (a halt). In process each is a worker spinning until the
watchdog, or dead — a crash, which a strict sweep counts ABNORMAL. So the C runs in a child first, and the case FAILS
by a timeout or a non-zero exit (`aes_event._vet_returned`: one assertion, whichever child). Which child:
- A DOOR USER — a core that reaches a hook: a FRESH INTERPRETER with the door bound, once before the differential
  (`aes_event.run_guarded` / `returns_in_a_child`; `aes_event.refusal` is where a frame's values become its C
  arguments) — or THE ZYGOTE'S FORK where one runs (`door_child`), a routine's DECLARED child doors included
  (`declare_child_doors`: the file selector's GEMDOS replay — the fork runs that declared source first, as the
  interpreter would; a CASE's own `before` is a fresh interpreter still). Its hooks must be bound per child. Remembered per worker by CONTENT — routine, frame, binding and THE
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
  `case.run`'s that arms the candidate) of a real function of the library that serves NO hook, or serves a NAMED one
  (below), while the worker's dispatcher hook is the module's own refuser — and a door user's CHILD whose binding is
  the door's standard one (`aes_event.door_child`: a fork that answers what a fresh interpreter answered — exit,
  lines, frames handed, answer, image, and a timeout as the same exception; a routine that declares child doors of its
  own still gets a fresh interpreter). Every other fork — one that serves a hook its case's pass built, a seeded run,
  a test's stand-in core — is the worker's own. So is EVERY fork of a test that takes `monkeypatch` (`conftest.py`
  sidelines the zygote for it: the zygote holds the modules as the session started, and a patch on the fork's side
  would never run in its fork — measured, a patched arming that raises: exit 8 from the worker's fork, 0 from the
  zygote's). A process with no zygote (a script, a child interpreter, the bench; `AES_NO_ZYGOTE=1`) forks itself.
  Every fork test runs under BOTH makers.
- THE NAMED-HOOK CONTRACT. A fork that SERVES a hook is the zygote's only where the hook is NAMED:
  `aes_event.named_hook(module, attribute, hook)` — a module-level builder closed over no case; the zygote resolves
  the name and its fork opens the pass itself. THE HOOK MUST LIVE IN A MODULE THE ZYGOTE ALREADY HOLDS when it starts
  (`aes_event.ZYGOTE_HOLDS`: `aes_event` and everything it imports). The zygote imports NOTHING for a hook: a hook
  named in a battery's helper module made it import the battery (its resident size ×20, and every later fork dearer),
  so such a hook is served by the worker's own forks instead — say so beside it (`aes_switch.IDLE_HOOKS`). One name
  per hook object; a second `named_hook` of one object is refused. A request carries its own function object's types
  (nothing of the zygote's library is retyped per request), fractional seconds are honoured (`setitimer`), and the
  zygote's own stderr is line-buffered (a hook's refusal printed before the C aborts is not lost, nor replayed into
  later forks).
- IT STANDS IN ONLY WHILE THE FROZEN MODULES HOLD THE VALUES IT WAS FORKED WITH (`aes_event.FROZEN_MODULES`, checked
  by identity, a name at a time, before each fork: `_as_the_zygote_froze_them`): a value rebound WITHOUT the
  `monkeypatch` fixture — `unittest.mock`, a plain assignment — sidelines it as the fixture does. **A LAZY CACHE IS
  FROZEN BY ITS SHAPE** (`aes_event.LAZY_CACHES`, by module): a module-level name bound from None, ONCE, by its first
  asker to an answer that is the same in any process — `isr._BENCH`, the cross-compiled blob — is no patch, and held
  frozen at None it put a process's zygote out of use FOR THE REST OF ITS LIFE from the first test that loaded the
  blob (every transcription pin does; measured: one battery alone, 1,066 forks by the zygote; after one file of
  another, 0 — and the suite stayed green, the lever silently off in most workers). The ONE transition None → its
  first value is the cache's own; bound AGAIN (a `mock.patch` of the blob, a sweep's bench put back in a `finally`)
  it is a value rebound like any other. A new lazy cache in a frozen module must be named there;
  `test_a_lazy_cache_is_frozen_by_its_shape_none_to_its_first_value_and_no_further` holds the rule WITH NO ZYGOTE
  (the blob's own test skips with the zygote off). A test that
  MEANS the zygote while it patches sets `aes_event.ZYGOTE_SIDELINED` to `aes_event.MEANT_UNDER_PATCHES` (not False).
- WHO MADE THE FORKS IS A MEASUREMENT, NOT AN ASSUMPTION: `AES_FORKS_REPORT=1` makes each process print, as it ends,
  `{"the zygote's forks": N, "this process's forks": N, "fresh interpreters": N}` (`aes_event.FORKS_MADE`). Any claim
  about the zygote rests on it: a worker whose line shows NO zygote forks has lost its zygote. A whole run today: the
  zygote's 5,768, the workers' own 108, fresh interpreters 176.
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
- `aes_event.settled` / `settled_in_windows` / `settled_where_stored` + `MASK_WORD_AND_SPL` settle a row's bytes
  that differ by nature from one run and `register_row` registers it (ONE SETTLING, ONE REGISTRAR, above);
  `run_core_steered` / `run_layer_case` are the trial loop of a steered case, over `steered_as_needed` (above).
- WHAT THE EVENT LAYER'S C CALLS OUT THROUGH HAS ONE SPELLING, the event layer's own: `aes_event.vdi_hook`,
  `handed_routines()` (the four fork functions, justretf, the VDI's default_user_cur), `POLLED_FUNCTIONS` (the
  keyboard's and the locator's polls, and vex_curv — ap_tplay's exchange of the cursor routine; its vex_motv is
  `aes_gsx.REACHED_FUNCTIONS`'),
  `SERVED_IN_A_FORK`, `TRAP_FRAME_DROP`, `FORK_CODE_SLOTS`, `EVENT_LAYER_HOOKS` / `EVENT_LAYER_DROPS`. A layer's
  helper module holds aliases, never a second definition (`aes_evinput.HOOKS`, `CURSOR_HOOKS` built on them); the
  door's own bindings take them by derivation the day an entry that polls is rebound (`polls_in_c`).

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

The door never lays the Line-F mask word `$cc44` into the C's image (a delivery's write of it is left out). A ROM caller's
own non-empty masked return rewrites that word after its last door call; the C makes none and keeps the word as it found it.

Of the three mechanisms the foundation designed, ONE is still not built (the first); the other two were built by band 4 wave 2:

- **The Line-F handler's Malloc(100) and 100-byte copy**, which a rebuilt ROM must keep so every later TPA block stays
  put (its mask word then differs forever, by nature). The copy carries ORIGINAL ROM code addresses as data — the
  handler's `movea.l #$fee900,a0` and 38 bytes of the call table's head — kept at the original's value and NEVER
  relocated, the opposite policy to the fork functions below: on a rebuilt ROM, any Line-F executed jumps through
  `$fee900` into unrelated bytes. "Nothing else about Line-F is observable" holds only while SP is in the kit's stack
  band: a case on a UDA's stack (inside THEGLO) or on the dispatcher's stack at `$8c1a` puts the exception frame and
  every Alcyon `link`/`movem` frame in COMPARED RAM, and needs a stack `dropped_windows` entry (the
  `LINEA_STACK_WINDOW` precedent).
- **A real process switch — BUILT.** On target the switch is the ROM's own bytes (`src/aes/switch.S`, THE SWITCH kind
  below) and a yield through our whole dispatcher is a priced row; off target it is a model behind a per-case switch
  (`aes_switch.scheduling`, above). What the design said of it holds: savestate's CPU state in the UDA is compared
  byte for byte ONLY by the `.S` rows, entered with one register file on both shores; for a run through C it is a
  by-nature drop, cut to what the ROM's run stored (the caller's saved D1/D2 for the bare yield, the whole context for
  a compiled caller), and savestate's `lea $8c1a,sp` puts disp's frames in compared RAM — the dispatcher's stack is
  dropped by name and, on our shore, PUT BACK as our run found it. Rows that switch WITH A DELIVERY and through a
  foreign process are built too (TIER 3: A ROW THAT SWITCHES, above: five pilots, one of them taking its key at a poll that is no idle); what remains is the wave's own —
  every blocking entry and door user as such a row, and the modelling they retire.
- **The RELOCATION of a ROM-made fork queue for our blob — BUILT** (A CODE ADDRESS IN COMPARED RAM IS RELOCATED, NEVER
  DROPPED, above): forker is priced over queues the ROM's own ISRs filled, its recorder's three arms are rows on both
  blobs, and no row drops a code address. forker's `jsr (a0)` is `staged_call.h`'s `call_alcyon_pointer` — off target
  the ONE register-carrying hook, bound by a case to the candidate's fork functions by their ROM addresses
  (`aes_event.handed_routines()`; the VDI's `$fcff0a` default_user_cur among them for a playback); on target a queue
  entry's code is the function's own plain-C entry (`aes_<fn>_fork`). Every forkq caller queues a fork function by an
  IMMEDIATE ROM address (pushed, or — ap_tplay — stored in the local its forkq call pushes), and forker's recorder and
  ap_trecd compare against them: sixteen instructions, `aes.FORK_FUNCTION_IMMEDIATES`, CODE values a C port stores as
  the ROM's and a rebuilt ROM as its own (`test_aes_door` holds them as every longword of the GEM text naming a fork
  function, and every forkq call as queueing one). (This said "a recording MADE under the ROM holds ROM
  fork-function addresses, and played back under our build they are queued as they are". Read from the bodies —
  band 4 wave 3's step T — that is true only WHILE IT RECORDS: ap_trecd turns each address into a NUMBER before it
  returns and ap_tplay turns the number back into the playing build's own fork function. What is queued as it is
  is a number that is none of the four; and what stays the ROM's on a blob is a record made inside a foreign
  window — A ROUTINE EVERY ARM OF WHICH LEAVES BY THE DISPATCHER, above.)

### The opcode switch's cases are LIFTED — `test/aes_gemsuper.py` (band 5 wave 1)

`aes_dispatch` (`$fe5d9c`) and `aes_marshal` (`$fe64e6`) have no machines of their own to stage: a call of the switch
is a call of one of its routines, marshalled, and every such routine already has a battery whose registered rows are
the ROM's calls of it over ROM-made machines. So a case is not written, it is LIFTED:

- `ARMS` is the inverse of what each arm's instructions read — `{the routine: (its frame, its machine) → Call}`, the
  opcode, int_in and addr_in a program would hand for the arm to make that very call. `lifted(<a registered row's
  name>)` gives the call, the row's machine and its kind (a row that returns, one taken through interrupts, one that
  switches); a row renamed in its battery reds this module's import by name. `at_the_switch` / `at_the_marshal`
  stage it (arrays in a band of their own, every word past what the call hands STALE; the parameter block and
  control for the marshal).
- A call no row gives (an inline arm, the default arm, a second value of a word) is a `Special` over a row's
  machine: `call(arguments)`, or `again(the lifted call)` — `with_words({index: word})`, `top_bytes`.
- BY STYLE (`style`): a door user's arm runs under the event door with every frame held (`aes_event.run_guarded`,
  registered by `aes_event.register`); the event layer's own under its layer's hooks (`run_layer_case`,
  `register_row`); an arm whose routine traps into GEMDOS over its battery's scripted or replayed trap, the C first
  in a fork made inside the open pass.
- A wake is the routine's own row that switches with the arm's entry and arguments (`switching_row`): the same
  deliveries at the same idles — held on the ROM's run that the arm adds no wait.
- THE RULE A NEW ARM OWES (`test_every_word_an_arm_reads_takes_two_values_across_its_cases`): each word of int_in
  and longword of addr_in the arm reads takes two values across its cases; a word the ROM's arm never reads is
  `UNREAD` in `ARMS` (handed stale, and the ROM is asked that it reads none). It is necessary, not sufficient — two
  values can be one answer (a flag, a rate both rows set to 0): the mutation sweep (`in(k)` made 0 and made 1) is
  what says a word is read.
- THE MARSHAL'S FRAME is one host slot (`HOST_SLOT_AES_MARSHAL_FRAME`: the 62 bytes, then sixteen that MODEL what a
  caller leaves above a frame — the saved A6, the return address, the arguments — which a case stages and the C
  never writes: `a_caller_s_words`). A copy back of int_out past the frame reads the model off target and the real
  stack on target; past the model the host refuses by name. One slot for every process until wave 3.

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
* **THE ONE RULE FOR A C TWIN'S ROWS, when its routine ships as its `.S`** (band 5 wave 1; stated here once): a
  twin's row OVER the bar is in the table, verdict `transcribed` (above). A twin's row that measures UNDER the bar
  would print with a blank verdict beside its siblings' `transcribed` and read as C that ships — so it is
  registered VERIFIED AND UNPRICED instead (`priced=False`), LISTED BY NAME WITH ITS NUMBER in the census
  `test_tier3.UNPRICED_AT_A_ROM_ENTRY`, and its second differential and cycles are held by its own battery
  (takeerr's twin, 1.04; pgmld's two arms that reach Mshrink, 1.02). The rule is applied to the AES's twins from
  band 5 on; earlier components' twins under the bar still print `ok`, and are theirs to bring under it.
* **The build contract** (`atari/target.mk`): `TRANSCRIBED_ENTRIES`/`TRANSCRIBED_SOURCES` are what the
  ROM build links for these routines and `TRANSCRIBED_C_CORES` the C twins it must not. The Tier 3 blob
  links both, because it measures both. The sources are `src/vdi/*.S` and `src/aes/*.S` — the table's
  components' — and NOT `src/*/*.S`: the BIOS's `trap.S`/`isr.S` and GEMDOS's `trap1.S` are entries of
  another kind, with no row, and every `.globl` of a listed source must be a row.
* **The declarations** at the end of the header: each entry as a LABEL a C caller reaches through glue
  naming the row's registers as clobbers — a plain C call of one does not compile — and
  `TRANSCRIBED_CORE`, the attribute every C core is defined with (`noipa`: never inlined, cloned or
  register-allocated across, so a call of it stays a call glue can replace).

**The BIOS's four interrupt handlers — no row, the same rule and the same pin.** `src/bios/isr.S` is the HBL, the
vertical blank, timer C and the ACIA handler as the ROM has them, with the ROM routines they reach by `bsr` (Scrdmp,
the cursor's blink and its cell inversion, the Dosound driver's step, the floppy's VBL service to its `flock` gate).
Their C (`hbl.c`, `vbl.c`, `timerc.c`, `ikbd.c`) is a TWIN: Tier 1 proves it, its Tier 3 rows keep their written
entries, and no entry calls it. Two things a C body under a handler cannot do sent them there, beside its ratio:

* **keep the register contract.** A handler calls RAM vectors, and the ROM gives the routine there the whole
  register file. A `jsr` cannot be told to lose A6 by a clobber (`staged_call.h`; an OUTPUT operand in A6 does tell
  GCC, at a cost over the bar, and is not used), the C blank holds a pointer there, and the VDI's
  cursor routine in `_vblqueue`'s first slot returns with A6 changed whenever it redraws — the blank after a mouse
  move never returned. No Tier 1 case can stage that (the host has no register file): `isr.keeps_nothing`, a staged
  routine that leaves all ones in D0-D7/A0-A6, is run under the blob's entry at each call.
* **stay off the interrupted stack.** GCC's register save under a call that keeps to nothing was 40 to 52 bytes a
  handler, on the AES dispatcher's 640-byte stack (the stack reading, further down; STATUS's KNOWN THIN MARGINS).

THE BYTE PIN IS THE TABLE'S (`transcription.pinned_region` / `assert_transcribed`), declared in each handler's
battery; a routine of `isr.S` is named by `isr.TRANSCRIBED_AS`, because the BIOS's `addrs.h` names carry no `ROM_`.
A `bsr` from one region into another is `Relocated` to the exact displacement the blob's layout gives. NO call
leaves for C: timer C's auto-repeat calls the keyboard's queue-a-key routine (`$fc2c42`), which the rest of the build
has as `kbd_queue_key`, and a thunk into that C cost the interrupted stack 52 bytes on its mouse arm — so the routine
is laid out in `isr.S` as well, the ROM's bytes for its one interrupt-time caller (606 bytes that exist twice in a
build: the price of the ROM's frame under an interrupt). NO BUILD STORES THESE ENTRIES IN THE FOUR VECTORS YET — the
ROM build links no handler — so that store is an unpinned surface (STATUS). An unreconstructed arm
inside a transcribed routine is a field of `trap #7` laid over the ROM's own words, so the branch round it stays the
ROM's (`test_past_its_gate_the_floppy_s_service_halts_and_its_return_is_where_the_rom_has_it`).

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

**THE SWITCH is a third kind of `.S`** (`atari/target.mk`: `SWITCH_SOURCES`; `src/aes/switch.S`, `src/aes/irq.S`): the
hand 68000 that has NO C SPELLING — the process switch (dsptch, the mask brackets, gotopgm, savestate, switchto:
`$fe387c..$fe395b`), the interrupts' glue with drawrat and justretf (`$fed3be..$fed477`), and disp. Not table rows:
there is no C twin to exclude, and no thunk may stand over an entry that builds a frame from its caller's return
address; an entry carries the name the C calls (`aes_dsptch`), and the headers a source includes are assembler-safe
(`__ASSEMBLER__` guards in `aes/switch.h` / `aes/evsync.h`). `transcription.SWITCH_ENTRIES` is the kind's table —
`{entry: SwitchEntry(rom, bytes, exits)}`, its lengths derived from the addresses, `exits` the symbols of OUR build an
entry's bytes name where the ROM's name the ROM's — held to the sources' `.globl`s and to each entry's pin
(`test_aes_switch.py`, `test_aes_irq.py`). No entry reaches the AES's ROM text, and NO WORD OF EITHER BLOB NAMES A ROM
ADDRESS OF THE KIND (`test_aes_irq.py`: every even longword of the blob scanned; the ROM's own sites that still do are
a held list, `OWED_BY_ROUTINES_NOT_RECONSTRUCTED`, against the census of the ROM's code immediates — port one and
forget to re-point it, and the list reds). THIS IS THE PROJECT'S "C FIRST, `.S` WHERE C CANNOT MEET THE BAR" APPLIED
TO CODE THAT HAS NO C AT ALL: everything round it that can be C is C (`src/aes/evdisp.c`).
- THE BYTE-EXACT REGIONS are pinned like any transcription (`pinned_region` / `assert_transcribed`), a word that names
  code a `Relocated(ABSOLUTE, None, why, thunk=<symbol>)`: dsptch's `jmp` (our disp); the glue's three `jsr`s (local
  thunks that take its pushed WORDS into the C call) and its two fork functions pushed by value (our entries). A `jsr`
  of our own entry where the ROM's word named a ROM routine is spelt `M68K_JSR_LONG(entry)` (`m68k_encodings.h`: gas
  would shorten it to `jsr <d16>(pc)`).
- **THE `stream` KIND** — for a routine Alcyon COMPILED that must still ship as assembly (disp: savestate reads its
  frame through A6 and hands it back another stack, a contract no compiled function keeps). Its calls are Line-F
  words, which would run the ROM's code from inside our build: so it is declared `transcription.stream(lo, hi, symbol,
  {ROM address: CallWord(routine, symbol)})` and held by `assert_stream` INSTRUCTION BY INSTRUCTION — each Line-F CALL
  word named (the ROM's table entry must reach `routine`; ours is `jsr symbol`), each branch's displacement the ROM's
  target followed to where our stream holds it, every other instruction equal, no PC-relative addressing, a Line-F
  RETURN refused (end the stream before it and prove it dead), the symbol's size exactly the stream's. disp's six
  substitutions: savestate, disp_act, mwait_act, forker, idle, switchto — the two halves of the switch by their own
  entries, the four C routines through local thunks.
- WHAT A PIN OF THE KIND DOES NOT REACH IS HELD BESIDE IT: `aes_switch.vet_a_thunk` (a thunk's body, instruction for
  instruction: which C it calls, its argument slots, a word's sign extension) and `vet_laid_end_to_end` (the source's
  symbols tile its text; after the last, the assembler's fill and no instruction — an `rts` after a `.size` passed
  every pin before).
- A `.S` ENTRY WITH A REGISTER CONTRACT AND BY-NATURE MEMORY (the glue) has no Tier 3 row: `aes_switch.vet_the_glue`
  is its differential — the ROM's glue and each blob's over one machine with one register file (an arrival of the
  ROM's own interrupt code: `glue_arrival`), the private stack and a queued fork code held as what they are.
- **A CODE ADDRESS THE BUILD HANDS THE OS IS INSTALLED BY THE BUILD.** A routine that hands the VDI a routine's
  address by value (gsx_setmb_aes: vex_butv / vex_motv) keeps handing the ROM's until somebody re-points it — and then
  the `.S` that replaces the routine is dead weight, every guarantee proved of it is proved of code the shipped path
  does not enter, and no differential sees it (the host must store the ROM's address to stay exact). So:
  `ALCYON_ROUTINE(AES_ROM_<X>, aes_rom_<x>)` at the site (the host the ROM's address, the target ours), the six slots
  relocated at Tier 3 (above), the scan of both blobs, and one test of the shipped path END TO END — over the machine
  OUR gsx_init left, the ROM's own VDI mouse interrupt enters OUR glue and spends 0 cycles in the AES's ROM text.
- **THE DERIVED STACK CHECKS — a `.S` entry that calls C on a stack the ROM sized.** Byte-pinning the entry says
  nothing about the C it calls: GCC's frames are not Alcyon's, and a stack the ROM sized for its own (the dispatcher's
  640 bytes, the glue's 92 and 96) can be overrun by a build whose every differential is green — into the globals
  below it. A MEASURED depth is met by case choice (the first check here was asked of the one path that is not the
  deepest, and a frame 300 bytes deeper passed it). So THE DEPTH IS READ OFF THE BUILD (`aes_switch.StackReading`):
  every instruction of every function reachable from the entry, each one's effect on SP followed down every branch,
  each call's callee added under the depth at its site; a call through a register is the functions THAT REGISTER holds
  by value where the call is made (read back through its block to the load that reaches it; a function GCC spilt to
  a frame slot too); a `trap #2`'s depth is answered beside the bound, for the measured need under it; the reading
  REFUSES what it cannot follow, EACH SHAPE BY NAME — an instruction that sets SP it does not know, two paths that
  meet at different depths, recursion, A CALL THROUGH A POINTER OF THE MACHINE (read out of memory or handed in:
  followed only where its caller DECLARES what the pointer can hold — `THROUGH_A_POINTER`: forker's four fork
  entries, drawrat's two cursor routines; the declarations held to the snapshot), a register nothing loads, a trap
  other than `trap #2`, a jump through a table, a path that runs off a listed body. Held to the truth by runs (the
  reading's deepest trap is EXACTLY a run's; the glue's deepest path is its deepest case).
  SINCE BAND 5 WAVE 2 (a process's stack: `test/aes_stack.py`, `test_aes_stack.py`) the reading also FOLLOWS a frame
  pointer's `link` / `unlk` and `lea d(a6),sp`; the build's halt (`trap #7` ends a path); a routine that LEAVES its
  stack as a declared leaf (`leaves_the_stack`: dsptch, 30 bytes read off `switch.S`'s own listing and measured); a
  register's loads DOWN THE FUNCTION'S OWN PATHS, each slot of the frame its own place (so `aes_mn_do`'s A2 needs no
  declaration, and a call through an argument's slot is not a function spilt to a local's); a routine that calls
  what ITS CALLER hands it, read per call site (`calls_what_it_is_handed`: everyobj); a branch INTO another routine,
  from where it lands; an application's routine as a declared callee of no listing (ob_user: the `jsr` counted, and
  `deepest_to` says how far down it is entered); a DECLARED EXCEPTION WORD (`takes_an_exception`: gsx_mfsave's
  `$a000`, the bytes measured). And it REFUSES, by name: an instruction of no kind it knows, a word objdump does not
  decode (a Line-A trap, a Line-F call word) undeclared, SP set from anything but a constant, an `rts` off anything
  but the return address, a jump out under the function's own pushes, a call through a register one path never
  loads, a label listed twice. A PROCESS'S BOUND has four terms, each OF THE BUILD THAT SHIPS — our frames by chain,
  the OS under a trap BY VDI CALL with THE BLOB'S OWN VDI on our shore — handlers and raster engines (`os_needs`;
  below) —, the nest with the horizontal blank
  (`nest`: 252), and what an application's routine is left — and its findings are PINNED AS NUMBERS, the verdict
  among them ("N spare"; "over by N" while it was): a finding is asserted, never an expected failure (a strict xfail
  hid a 120-byte growth). `python test/aes_stack.py` prints the table; a pin that moves is re-pinned with the
  frame's or the call's name.
  AT A TRAP THE BOUND IS CALL BY CALL (`aes_stack.trap_sites`, `at_its_traps`; the frame diet, 2026-10-10). The
  deepest trap of a listing and the deepest need under a trap are different calls — a fill's and a text's — and
  charged together they are a call no path makes. So every TRAP SITE (a call, by a routine that does not hand an
  opcode on, of gsx_ncode / gsx_1code or of the trap's own routine) is charged ITS call's need: the opcode READ OFF
  THE LISTING at the call (`pea (N).w` before the image's push; an Alcyon caller's `move.w #N,-(sp)`), else what its
  function is DECLARED to ask (`OPCODES_DECLARED`: gsx_attr, gsx_tblt — held to the C body's own `VDI_ROM_*_OPCODE`
  names and to the listing's immediates), else THE WORST NEED OF ALL (pinned: gsx_xline's one sibling call). Every
  opcode a site can ask must be MEASURED on every shore (`THE_ROUTINES_BESIDE` runs the three calls no scenario
  takes on its own stack); an unmeasured one is refused by name. The coarse sum is kept beside it as a finding.
  The opcode is read ONLY where the listing says one: two pushes a branch chooses between, or a store into the
  opcode's slot after the push, is refused by the function's name (`_opcode_read_at`).
  WHOSE VDI RUNS UNDER THE TRAP IS A DECLARED MAPPING, AND HELD (`aes_switch.vdi_table_mapping`,
  `aes_stack.who_ran`). The C dispatcher calls the function its opcode's slot of the ROM's two tables names
  (`$fd372c`, `$fd37c8`: ROM data, so on a ROM-booted machine THE ROM'S handlers — for a pass every "need of our
  VDI" was theirs + the dispatcher's 32, and a v_gtext frame 100 bytes deeper moved no pin). The staging maps ALL
  71 slots to the blob's own handlers: a C handler through an image-only thunk laid in the staging's own band
  (`pea image / jsr / addq / rts`: the build's shape for a routine a table calls without an argument), a handler
  that ships as its `.S` directly on the shipped blob. A slot whose handler the blob does not link is REFUSED BY
  NAME; a test holds, per opcode priced, that the blob's handler is entered and the ROM table's entry never — the
  handler looked for being the one of THE OPCODE'S NAME (`the_handlers_named_for`: `VDI_ROM_<NAME>_OPCODE` ->
  `vdi_<name>`, off the symbol table), not the one the mapping's builder chose.
  THE LINE-A VECTORS ARE MAPPED THE SAME WAY (`aes_switch.linea_vector_mapping`, `aes_stack.engines_ran`). A
  handler that ships as the ROM's instructions reaches its raster engine through a longword of RAM — the ten the
  boot fills from the ROM's CPU set (`vdi/linea.h`, LINEA_VECTORS) — and on a ROM-booted machine those name the
  ROM's engines: with only the 71 slots mapped, the blob's handlers ran THE ROM'S raster code. So on the blob that
  ships its transcriptions each vector is mapped to the blob's engine of the ROM routine's own name
  (`LINEA_ROM_CPU_BLIT` -> `linea_rom_cpu_blit`), vetted to hold the ROM's first, REFUSED BY NAME where the blob
  has none — the console's four declared left. THE BENCH BLOB'S VECTORS STAY: its C calls each engine's twin by
  name after `require_cpu_routine` has checked the vector holds the ROM's, and a vector repointed there halts.
  `engines_ran` holds both: under no opcode priced is an engine of the ROM's entered, and the blob's own are.
  A NEED IS A LOWEST STORE; THE VERDICT CHARGES THE BOUND ON SP (`unstored_runs`, `unstored_under`,
  `needs_bounded`): every allocation of the listing nothing is stored under is found — `lea -N(sp),sp`, `subq`, a
  `link` ON ANY ADDRESS REGISTER — over EVERY instruction the listing holds, whatever labels it (`listed_runs`: a
  body the symbol table does not size is scanned like any other). "Stored under" is read DOWN THE STRAIGHT LINE: a
  push, a `pea`, a call or a store to `(sp)` before a branch, a return or SP raised; each instruction on that line
  goes through the reading's own `stack_effect`, which refuses one it does not know. The ones a run of each opcode
  REACHES are found by stops (chunked: the oracle's door holds 64; every `trap #2` is a stop too, so a place is
  armed again for the next call), and THE LARGEST is added to that opcode's need — the copy-raster's 76 bytes of
  locals under the two blits, the line's and the fill's 20. The dispatcher's stack carries the same term
  (`test_aes_evdisp_model.py`: 0 under its five calls). NOT bounded, and said in the report: the BIOS under
  `trap #13`, and the vectors an application or the machine owns (USER_TIM / BUT / MOT / CUR).
  THE PRECONDITION of every need: the workstation's attributes as the AES leaves them (an application's text
  effect or line width on the physical workstation deepens the AES's own calls there, on the ROM as on ours).
  THE GATE IS THE SHIPPED BLOB; the bench blob's bound is pinned and printed beside it, and gates nothing.
  WHAT AN INTERRUPT NEEDS ON TOP IS MEASURED TWICE: the ROM's own handlers from their vectors (`interrupt_needs`,
  kept by content — cold-sweep a mutant of it) and THE BUILD'S OWN ENTRIES (`our_interrupt_needs`: what a ROM that
  ships installs); and the OS under a trap twice too — the ROM's VDI and OUR C VDI linked under the trap
  (`our_loop_run(our_vdi=True)`). A check that adds THE ORIGINAL's handlers to OUR frames passes a build that ships
  its own, and for a wave it did: with a C body under each entry (a pushed image pointer, a `jsr` and GCC's
  register save) ours needed 192 / 188 / 152 for the ROM's 140 / 140 / 100 — 356 + 344 = 700 of 640. The entries
  are the ROM's own instructions now (`src/bios/isr.S`: "What ships as the ROM's own instructions") and the two
  measurements are equal — ONCE EVERY ARM IS MEASURED: the first equality counted eight ticks none of which injected
  a key repeat, and the tick that injects Alternate + an arrow (a mouse packet, under timer C) was 196 through a
  thunk into C for the ROM's 144. `_needs_measured` takes the worst of a handler's arms now, the injecting ticks
  among them, each state made by the handlers' own runs: 140 / 144 / 100 on both shores — with the horizontal
  blank's 8 under them (`aes_stack.nest`: 252) the dispatcher's bound of 292 is 544 of 640,
  held on both blobs with the build's own VDI handlers under its trap
  (before the frame diet, 2026-10-10: 356 + 244 = 600); 78 / 60 / 46 of 92 / 92 / 96. A recompile that deepens any frame on a path — one no
  case runs as on the others — reds by name.

**An ALCYON ENTRY `.S` is glue, not a transcription.** When AES C hands a routine BY VALUE to ROM-shaped code that calls it
the Alcyon way — ob_draw passing just_draw to everyobj (`$fea08c`) — the host case binds the ROM address to the C core, but
on target the value must be our own routine: the ROM's would run the ROM's AES code inside our build, which the (V) bench
refuses by name, and a rebuilt ROM would not hold. `src/aes/obdraw.S`'s `aes_just_draw_alcyon` repacks everyobj's 10-byte Alcyon
frame into the GCC call (the image base, then each word sign-extended into its slot) and enters the C core. It has no ROM
bytes and no row of `include/transcribed.h`: `atari/target.mk` lists it as ALCYON_ENTRY_SOURCES, filtered out of
TRANSCRIBED_SOURCES so the transcription `.globl` pin stays exact; Tier 3 counts its cycles as glue (`bench/tier3.py`'s
ALCYON_ENTRIES, T→G, like a generated thunk); and `test_transcribed.py` pins its `.globl`s to exactly that list, outside the
table. No host surface sees it, so its mutants are judged by Tier 3's second differential.

**A `.S` THAT LEAVES ADDRESSES OF ITS OWN TEXT IN RAM — mapped through the relocation registry, never dropped**
(`src/aes/gemdosif.S`: pgmld, band 5 wave 1). pgmld reaches `__DOS` by `bsr`, so the return address `__DOS` parks
(`$8c22`) is a site inside pgmld, the command tail it hands Pexec is the address of a zero word of its own text, and
`__DOS` leaves by `jmp (a0)` with that site in A0: the ROM's addresses on one shore, the `.S`'s own labels on the
other. A transcription row drops nothing, so they are RELOCATED: `aes_event.TEXT_SITES` (a member of
`CODE_RELOCATIONS`: the ROM address ↦ the local label of the `.S`, mapped where our run ends) and, for this kind
alone, the register file too (`tier3.map_registers`). A battery whose staged trap RECORDS such an address declares
the longwords of its ledger that can hold one (`aes_event.declare_text_site_slots`, in the recorder's own module:
`test/aes_gemdosif.py`). The mapping is in force ONLY FOR A RUN THAT CAN PARK A SITE — the `.S` entry's own, and a
declared C caller's on the shipped blob (`aes_event.TEXT_SITE_CALLERS`: NONE YET — pgmld has no C caller, so no
thunk is generated and `aes_pgmld` on the shipped blob is still the weak C twin, which parks the ROM's sites as the
data they are; its first caller is the accessory loader, wave 3, whose pair in
`transcription.C_CALLERS_OF_TRANSCRIBED_CORES` — the table `test_transcribed.py` holds to the build's call graph
and the thunks are generated from — must be named there too: `test_aes_pgmld.py` reds while they disagree). A
register our run leaves holding the ROM's own site is refused by name before it is mapped, as a slot is.
To add a site: a local label in the `.S`, a row in `TEXT_SITE_SYMBOLS`, the slot if RAM holds it.

**THE DISPATCHER'S SAVE WORD IS COMPARED — but for ONE BIT on a row that DECLARES it**
(`aes_switching.THE_X_FLAG_ALONE`, `SwitchingRow.x_flag_differs`). dsptch pushes its caller's status register and
switchto parks the SR it is entered under: where a yield comes after arithmetic of the caller's own, the X flag in
`$8995` is the compiler's — Alcyon's in the ROM, GCC's in a build (the desk's rsrc_free binding where GEMDOS frees
the block: `$00` against `$10`). Measured over the registry, 294 of 298 switching runs hold the byte equal, so this
is NO kind of every row's: the two rows that need it declare it, the table prints the line under those two, and
nothing is left out of the compare — Tier 3 flips that one bit in the image our run leaves and compares the byte
whole. So N, Z, V, C and the system byte `$8994` stay compared; a declaring row whose bytes are equal without the
flip (a declaration it does not need) is refused; a non-declaring row whose X differs is refused like any byte.

**CALL ORDER ACROSS THE DOORS — `test/aes_trap_order.py`.** A routine that makes several calls out leaves an image
that says nothing of their order where they commute in memory (a buffer freed before or after the workstation
closed; a vector stored before or after the Setexc beside it). `aes_trap_order.on_both_shores(tier3, bench, row)`
measures a C row with BOTH runs watched at the four trap handlers (`trap #1`, `#2`, `#13`, `#14`: where the vectors
point, the same addresses on both shores) and answers two `TrapOrder`s — `names()` the `(trap, function)` list in
the order taken, `held(nth, witness)` what a witness longword held at the nth call (by default the two vectors GEM
takes, what it saved of each, and the mouse's hide count). Assert the ROM's list against what the source says, and
ours equal to the ROM's (`made`). It stages nothing and moves no cycle; it needs a Tier 3 row, so it is a surface of
the blobs, not of the host: THE HOST BUILD'S CALL ORDER IS HELD BY NOTHING (it takes no trap — its doors are hooks
and direct C calls), and is the same C the blobs are built from. The handlers are read BY VECTOR: a machine that
stages one stub behind two vectors is refused by name.

**A RECORDING, SCRIPTED TRAP PER VECTOR — `test/aes_gemdosif.py`'s `Recorder`.** For a routine whose GEMDOS (BIOS,
XBIOS) calls are the claim: the vector pointed at a staged 68000 handler that records each call's function word and
ITS FRAME'S OWN BYTES (never what lies above them on the stack: that is the caller's, and differs by nature), the
longwords the glue parked at that call, and answers the next longword of a script; `twin()` is the same effect on
the host. A routine that also SWITCHES binds it in its Tier 1 fork by `SwitchingRow.child_doors`. A handler's
instructions are cycles in both columns of every row recorded through it — keep it to what the glue itself parks.

**A CASE WHOSE FAILURE WOULD END THE SUITE GOES FIRST, IN A CHILD.** A host twin that halts by name, or walks a wild
pointer into the bus guard, takes pytest down with it: a mutant that does so is counted ABNORMAL, not killed. The
case that would catch it is run once more through `aes_event.refusal` (a child: its return code and what it left)
and placed BEFORE the in-process cases of its file (`…__held_in_a_child` in the batteries of band 5 wave 1).

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
case's parameters answering its group, None for a case that is no session's). Four batteries declare it (`test_aes_evmulti.py`
by its case's name, below): the file
selector's sessions (`test_aes_fs_input.py`), its priced sessions' cases (`test_aes_fs_input_rows.py`), and Tier 3 —
a sliced session's rows, companions and partition test (`test_tier3.py`). Nothing is added, removed or renamed — the
same items and ids, reordered inside their own module. `test/test_conftest.py` pins both: the distribution on real
runs of xdist, the order on each battery's own declaration.

A BATTERY'S MEMO IS BOUNDED AND ITS TESTS ARE GROUPED. A result holds the images its run left, sixteen megabytes each:
a `functools.cache` over a table of cases was TWO GIGABYTES a worker (ev_multi's battery, 93 results), and with no
grouping a steal handed the tests of one case to other workers, each of which ran the case again (1.8 times over under
`-n 8`). `test_aes_evmulti.py` keeps the last three cases (`lru_cache`) and collects the tests of one case back to
back (`pytestmark = collected_with(by=<the case's name>)`; a test that reads one case by a literal name is marked
`of_the_case(name)`), so a steal splits a case's tests at one boundary and no worker runs a case for one test of it:
2,100 → 587 MB, and with the two steering levers 36 → 7 CPU-s warm. Measure a new battery's peak RSS and its ROM runs
under xdist against serial before it lands.

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
   another tree. THE PROJECT'S `names.txt` IS ONE OF THOSE FILES (`derived.PROJECT_INPUTS`): a `cmt` added by a
   docs pass makes the next run derive cold, and a run in flight when it is edited loses the cache for the rest of
   its life — edit it before the suite run whose time is to be quoted, never during it;
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

A DERIVATION IN FLIGHT IS CLAIMED (`derived.py`'s docstring has the whole contract), so the processes that ask one
question at one moment make it ONCE — ten cold workers importing the registry side by side each made every derivation
(308–318 → 183–193 CPU-s with the claim; 360 → 275 in the suite's own cold collection). A process about to MAKE an
answer puts a claim beside the answer's place (a hard link: it fails where a claim stands); one that finds another's
claim WAITS and is then served the answer as any hit is. What makes it safe to wait: a claim whose maker is no more —
gone, stopped, or its pid another process's now — is taken over at once, and one that stood
`CLAIM_STUCK_AFTER_SECONDS` under one maker likewise; a claim that went with NO answer left means the derivation
RAISED there, and every waiter then makes it itself, UNCLAIMED and side by side (taking the claim in turn made ten
askers wait on one another's failures); a claim that names nothing readable has no maker; a place that cannot be
claimed is made unclaimed; a process that HOLDS a claim never waits; a waiter's rests GROW FROM ITS FIRST LOOK at a
question (5, 10, 20, 40 ms, then 50: a back-off that began after a whole second of one question never began — the
mean wait is 60 ms). NOTHING HERE DECIDES AN ANSWER: a claim is in no key and is no answer. A test that patches the cache's place
must leave no `*.claim` behind in the tree's own cache.

TO KEEP A NEW DERIVATION: decorate the function that makes the ROM's run with `@derived.kept`, hand it everything it
reads as arguments of a kind the key can read (a module global a test may patch becomes an explicit input), and add
its changed-input cases to `test_derived.py`. NEVER keep anything our build takes part in — a differential, a Tier
3 measurement, the bench blobs' runs: that is the suite's subject. (ONE exception, stated in `derived.py`: which
steering reasons a case needs — its trials run the candidate; the tree's key holds the candidate's library as loaded,
and the answer decides no verdict.) And the real-disk run's DELIVERIES are not
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
  `AES_DERIVED_SAMPLE_SEED=<anything>` (another sample of the served answers is made again);
  `AES_FORKS_REPORT=1` (each process prints who made its children as it ends: the zygote's forks / its own / fresh
  interpreters — THE ZYGOTE, above); `AES_STEERED_FOR_NOTHING=1` (the on-demand sweep of the steering reasons:
  THE EVENT DOOR, above); `RUN_SLOW=1` (the placement search and the other tests gated as slow). INTERNAL, never set
  by hand: `AES_DERIVED_TREE`, a process's tree key and the record it was made with, handed to its children.
- TELLING A COLD RUN FROM A WARM ONE: collection is 36–40 s a worker cold and about 10 s warm (pytest's own wall,
  ten workers, quiet at the start: 209 s and 1,560 CPU-s for a bare cold `pytest`, 146 s and 1,288 CPU-s warm —
  22,681 tests, 2026-10-07; before the kit read images in place and the zygote's lazy-cache fix: 231 / 170 s). A
  timing quoted without saying which is not a timing; for a cold figure empty `build/derived/` or set
  `AES_DERIVED_OFF=1`, and remember that ANY edit under the keyed tree makes the next run cold.
- WHAT MUST STAY EQUAL cold, warm and off (the content-neutrality check of any change here): the collected case ids
  and outcomes, the row hashes and scenario hashes over one pinned `boot_ram.bin`, the table's lines.

## The frame diet — `include/stack_diet.h`, and re-pinning the rows that switch

**WHY.** A process of the AES runs on a stack THE ROM SIZED for Alcyon's frames (the screen manager's 1,196 bytes,
the dispatcher's 640). GCC's frames at -O2 were half as deep again: read off the build (`test/aes_stack.py`) the
screen manager's deepest trap, with the worst VDI call under it and the interrupts' nest, was 284 / 294 bytes OVER. Most of
the difference is not the C but what -O2 spends STACK on to save cycles, in a build whose every address is
`image + constant` and whose every argument is a longword slot.

**A MARK** is `FRAME_DIET("no-<pass>", ...)` on one function's definition (directly above it, above `EVDOOR_TWIN` /
`TRANSCRIBED_CORE` where there is one): GCC's per-function `optimize` attribute, turning off for that function the
passes MEASURED to deepen its frame — `no-defer-pop` (a call's arguments left under the next call),
`no-optimize-sibling-calls` (a tail call's caller copies its own arguments into its frame),
`no-move-loop-invariants` and `no-function-cse` (an address, or a callee's, kept in a saved register for a loop),
`no-caller-saves`, `no-gcse`, `no-tree-dominator-opts`. 34 routines carry one — 33 of the screen manager's paths
and the VDI's `place_and_draw`, v_gtext's deep frame (the header says what each flag costs the stack).
Beside the marks, three STRUCTURAL cuts, each said where it is made: just_draw's four parts are
routines of their own (`noinline`: a part's registers lie only under that part's calls); `blt_corners` is one;
and three bodies are held by their one deep caller as its own — menu_down's by mn_do's pass, gsx_blt's by
gr_gicon's blits, bb_fill's by gr_rect — where the ROM calls (the extern routine stays, for every other caller and
for its own rows).

**UNDER THE TRAP, ONE CONTRACT** (`include/staged_call.h`, `call_vector_as_the_last_act`; the third pass). The VDI
dispatcher's call of its opcode's function keeps NO register round itself — a bare `jsr (a0)`, GCC told only what a
C call changes — as the ROM's dispatcher does not: the trap's entry has saved them all. Saved round the call they
were 44 bytes under every VDI function, on whichever process's stack the trap was taken. It is sound only while
NOTHING of the dispatcher's is live across the call, which no compiler checks: `test_vdi_entry.py` reads both
blobs' listings (after each `jsr (a0)` of the dispatcher, pops and the return alone), and the entry's C twin, the
one C caller, saves the lot round its own call (`dispatched_keeping`) and is held to that.

**THE GUARD** (`test/test_stack_diet.py`; GCC documents `optimize` as a debugging aid, so nothing is trusted):
every marked function is compiled twice under each blob's own flags — as marked, and with the marks off
(`-DSTACK_DIET_MARKS_OFF`) and the mark's flags on the command line — and the two must be the same instructions
(so a mark changes nothing but its flags FOR THAT FUNCTION), and other instructions than no mark and no flag at
all. AN `optimize` ATTRIBUTE DOES RESET ONE SETTING, which that comparison cannot see in a function without such a
loop: `-ffreestanding`'s implied `-fno-tree-loop-distribute-patterns` — a fill, copy or length loop under a bare
attribute compiles to `jsr memset` / `memcpy` / `strlen`, which a `-nostdlib` ROM has not. So the setting is spelt
INSIDE every macro that makes an attribute (`OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS`: the diet's and gemsuper's jump
table's), no source spells a bare `optimize(`, and a fill loop is compiled under each macro and held a loop. And the
bench blob is linked a second time with every mark off, which pins what the marks buy: the two bounds, and each
function's own frame without and with (never more with, less on one). The cycles a mark costs are Tier 3's.

**SEARCHING THE FLAGS FOR A FUNCTION** (how the 34 sets were found; nothing of it is in the tree):
1. build the bench blob with `-DSTACK_DIET_MARKS_OFF` and each combination of the candidate flags ON THE COMMAND
   LINE (seven flags: 128 links of ~6 s, side by side) — the guard is what makes a command-line flag and a mark
   the same thing;
2. read each blob with `aes_stack.reading(elf)` and keep, per function of the paths, what it holds on its deepest
   path and at its deepest trap (`reading.chain(function)[0]`);
3. per function take the FEWEST flags that give its smallest frame, and mark it;
4. take each flag off again, one link each, and drop the ones without which no frame is deeper;
5. `make bench`: a row that goes over the bar by a mark loses that mark, not the bar.

**RE-PINNING THE ROWS THAT SWITCH** (`tools/pin_recorder.py`, `tools/repin.py`). A change of the build's code
generation moves the pinned cycles of hundreds of rows at once (the frame diet: 555 pairs in 11 files). They are
re-derived FROM A RUN, never typed and never loosened:

    PINREC_OUT=$PWD/build/pins.jsonl PYTHONPATH=../../../tools:tools .venv/bin/python -m pytest -q \
        -p recreate_kit.watchdog -p pin_recorder -n auto test        # every moved pin still FAILS; each is recorded
    python3 tools/repin.py build/pins.jsonl .                         # what it would re-pin, and what it refuses
    python3 tools/repin.py build/pins.jsonl . --apply                 # then run the suite again

The recorder wraps `aes_switching.vet_on_a_blob` and `vet_the_table_s_price` and writes `(what the test holds, what
the run measured)` with the file of the test that asked; the rewriter replaces a pair IN THAT FILE — or, where it
does not spell it, in a test module it imports — and re-makes the ratio a `Priced(...)` line quotes. It REFUSES by
name: a record whose ROM-SIDE count moved (our build's change moves our count; the ROM's moving is a regression of
the machine or the deliveries, and the tool ends non-zero), a pair two rows share and move apart, and a pair neither
the recording file nor its imports spell, and A PAIR SPELT MORE TIMES THAN ROWS RECORDED ITS MOVE (two rows that
share a pair, one of which moved: nothing says which line is which, so neither is written). A file that spells the
same pair for a row nobody recorded is never touched (`test/test_repin.py`).
What it does not reach is red in the second run and is re-pinned by hand with its reason (the dispatcher's yield
and wait and its stack's four numbers, fs_input's slices, the glue stacks). The plugin is a module outside the
derivation key, so `test_derived`'s census of imported modules is red in a RECORDED run alone.

## `make gates` — the pre-commit gates as one command

`make gates` builds once (libraries, both blobs, snapshot, derivations, table) and then runs `make test`'s pytest,
`make guarded`'s pytest and the ROM build (`make -C atari -B all`) SIDE BY SIDE, each with its own log
(`build/gates/<gate>.log`), its own status file and its own pytest cache; it prints each one's last lines and ends
non-zero if any did. The same command lines as kit.mk's targets (PYTEST_ARGS / GUARDED_PYTEST_ARGS apply), the same
case ids and outcomes as the four run in turn. It starts by removing `build/gates/`, so two of them at once in one
tree overwrite each other's logs: one at a time. WHAT IT BUYS IS NOT THREE GATES FOR THE WALL OF ONE — the two
suites are the same CPU-bound work twice and ten cores are ten cores (side by side each takes about twice as long):
measured, 388 s against 389 s for the four in turn (309 s with the derivations made; 375 s and 2,985 CPU-s from an
EMPTY `build/` at 22,681 tests, 2026-10-07). It buys one command, one build and one set of derivations. It does not
`rm build/*.so`: the forced rebuild before a commit is still the committer's own first step.

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

* **A WARM Python sweep is BLIND to a mutant inside a kept derivation** (and to one of a module global a kept
  derivation reads). A harness mutant applied to the FILE changes the tree's key and runs every derivation cold (3–12
  minutes a mutant under load); applied AT IMPORT by a meta-path hook — the tree's files untouched, the key the
  unmutated tree's — the sweep is warm. But then the unmutated answer of a kept derivation is SERVED: two mutants of
  `aes_switch` (the ticks an interrupt's need is measured over; the bytes the OS uses under a trap) SURVIVED warm and
  are KILLED with `AES_DERIVED_OFF=1`. Run such mutants cold.
* **WHICH PART OF A BATTERY HOLDS A MUTANT is asked with `-k`**: a store that a comparison's drop could hide is swept
  against the tests that use that comparison ALONE, so "killed" is not the gift of an unrelated differential. For a
  twin's TAIL after a wake those are its wakes, host and blob as two runs (ev_multi's: host `-k "through_the_scheduler
  or woken_through or after_the_wake or tail_clears or leaves_the_sent_mark or key_typed_with or press_brings or
  woken_in_one_idle or through_the_menu"`, blob `-k both_blobs` — the hook road's `-k woke` is replaced by these: it
  now matches every id that says "woken", premises and pricing tests with them).
* **A host-only stand-in is swept through a test of its own**: a library that keeps a host slot held aborts the WORKER
  at the next in-process claim — ABNORMAL, never KILLED — wherever the zygote made the fork-first run (its own library
  is clean). The give-back is held by a test that makes the call twice in one fork
  (`test_the_qpb_s_host_slot_is_given_back_when_the_call_returns`).
* **A "mutant" that deletes a TEST's own assertion is no mutant of the code under test** — nothing tests a test. Say
  so where a sweep lists one. And CHECK THE BASELINE before trusting a kill: a mutant tree gone stale against the
  shared tree turned a baseline red into a "KILLED".
* **A control's own machinery is code**: the zygote's frozen-module rule had no test that the zygote still stood in
  after an ordinary test, and a neighbouring test passed or failed by which tests its worker had run before it. A
  speed lever needs a test that it is ON (`AES_FORKS_REPORT`), not only that the suite is green with it.

* **`pytest --collect-only -q` UNDER AN INVOCATION THAT ALREADY SAYS `-q` PRINTS `file: N`, NO IDS.** A script that
  builds an id list from it (a reversed-order run, a sweep's selection) gets an EMPTY list, and pytest handed no ids
  runs THE WHOLE SUITE — serially, if the script said so. Collect with one `-q`, and stop on an empty list.

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
│                       `aes_boot.py` (the ROM's own boot from a pre-init machine: the desk's and the accessory
│                       machines) and `acc/` (the test accessory's source and link script)
├── tools/              boot_snapshot.py (the snapshot), addrs.py (addrs.h as Python), preinit_snapshot.py (the
│                       two pre-init machines, `--cross-check`), accessory_disk.py (the test accessory and its floppy)
└── build/              gitignored: the candidate .so, the RAM snapshot (the ROM's own data),
                        bench/ — the cross-compiled blob and the Tier 3 table — and bench_shipped/,
                        the shipped configuration's blob and its generated glue; derived/ (the
                        derivation cache, by tree) and gates/ (`make gates`' logs); preinit.bin, preinit_acc.bin
                        and acc/ (the two pre-init machines and the accessory floppy they need)
```
