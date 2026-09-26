# Reconstruction status — TOS 1.02 US

**As of 2026-09-14.** Wave 1 is merged: the ROM is bootstrapped in Ghidra, the three evaluation tiers
each have a working instrument, and the first two XBIOS functions are verified with sharp differentials.
Read `../README.md` first for the three tiers a component is held to; `test/test_status.py` pins the
counts in this file against its rows.

## Components

| component | Tier 1 (functions verified) | Tier 2 (conformance ledger) | Tier 3 (cycle ratio) | state |
|---|---|---|---|---|
| boot | 0 | — | — | NOT STARTED |
| bios | 20 | — | 0.88–3.63x, every ✅ row priced (`make bench`); one ACIA-chain routine unpriced (`acia_take_byte`, which no case enters directly) | STARTED |
| xbios | 29 | — | 0.23–2.03x, every ✅ row priced; the shared timer programmer unpriced (register arguments) | STARTED |
| gemdos | 105 | — | 0.35–1.75x, every ✅ row priced; the three terminators verified and unpriced (they stop at a CHECKPOINT, so there is no second column) | STARTED |
| vdi + linea | 0 | — | — | NOT STARTED |
| aes | 0 | — | — | NOT STARTED |
| desk | 0 | — | — | NOT STARTED |
| data | — | — | — | NOT STARTED |

## Verified — xbios (29)

Each row is one function of the ORIGINAL ROM, run in place at its own address over the post-boot RAM
snapshot and compared byte-for-byte against the reconstruction (`../README.md`, Tier 1). The cost
column is the ORACLE's own count for one call — the instructions it executed and the 68000 cycles
they took — and the TIER 3 column is the same C cross-compiled by `m68k-elf-gcc` with the shipped
ROM's flags, run under the same oracle over the same case (`bench/tier3.py`; `make bench` prints the
table, `test/test_tier3.py` gates it at <= 1.10). Both are as the oracle reports them, including the
1 instruction / 40 cycles its reset charges before either entry; the ratio is net of that on both
sides. Each ratio is also a SECOND DIFFERENTIAL — the m68k build must leave the same image, return
value, callee-saved file and chip traffic as the ROM.

| Addr (ROM) | Name | Cases | Cost (insns / cycles) | Tier 3 (recreate / original) | Status | Verification |
|---|---|---|---|---|---|---|
| `0xfc1510` | `Random` (XBIOS $11, `src/xbios/random.c`) | 19 | 44 / 810 seeding, 39 / 710 advance | **0.62** seeding (30 / 520), **0.67** advance (25 / 488) | ✅ verified | both branches of `tst.l random_seed`: the snapshot's own unseeded machine, and seven system-tick values through the `asl.l #16` / `or.l` seeding arm including ticks with the high word set; eight seeds across the SIGNED 32x32 helper's edges (either operand negative, both, and the two values `neg.l` leaves alone); the 24-bit projection asserted against the state the diff compares byte-for-byte; a 64-case fuzz over seed x tick. The ROM's call into Alcyon's `lmul` at `$fc4b28` executes in the ROM like any other instruction, so this is also the pin that ROM-internal calls work. Poison on every parametrized case |
| `0xfc2ea4` | `Giaccess` (XBIOS $1c, `src/xbios/giaccess.c`) | 49 | 17 / 260 read, 18 / 270 write | **0.60** read (14 / 172), **0.74** write (16 / 210) — incl. the IPL bracket (`ipl.h`) | ✅ verified | all sixteen registers the four-bit select latch can name, read and written, against a declared entry file with a distinct byte per register — so reading the WRONG register diverges on the value rather than by luck; the ordered PSG access ledger compared on every case (the chip is off-image, so nothing in the memory diff could see it); five data words proving only the low byte reaches the port; eleven `reg` words proving the direction bit and the register both come from the LOW byte alone. A decoy planted at `$ff8800` pins that the ports reach the seeded model rather than the image, which is the claim ROM mode has to get right. Poison on every case |
| `0xfc0aac` | `Getrez` (XBIOS $04, `src/xbios/getrez.c`) | 263 | 5 / 82 | **0.95** (4 / 80) | ✅ verified | the three ST resolutions the shifter really sits in, each declared with `io_seed`; a 256-case sweep of every byte the register could hold, pinning `and.b #3` against the `$07`/`$ff`/`== 2` variants; a decoy planted at `$ff8260` proving the register reaches the declared I/O map and not the 16 MB image; the declared/undeclared PAIR over one routine — undeclared it refuses by address and prescribes the `io_seed`; `hw_seed` refused by name as the wrong door. THE FIRST RECONSTRUCTION IN THIS PROJECT TO READ A HARDWARE REGISTER. Mutation 4/4. Poison on the parametrized cases |
| `0xfc0aa6` | `Logbase` (XBIOS $03, `src/xbios/logbase.c`) | 7 | 3 / 72 | **1.50** (4 / 88; +16 cyc = the image-pointer load, accepted) | ✅ verified | the snapshot's screen at `_memtop`; six bases incl. values no Setscreen would store — the routine reports, it does not validate |
| `0xfc28f6` | `Iorec` (XBIOS $0e, `src/xbios/iorec.c`) | 12 | 5 / 98 | **1.48** (9 / 126; accepted: image pointer) | ✅ verified | the three rings, asserted distinct and tied to the addresses Bconstat's drivers walk; devices 3-5 reading `Rsconf`'s opening instructions as addresses (unbounded, reproduced); the low-word index; and device `$2000`, whose `$8000` index SIGN-EXTENDS to `$fba902` below the table — the two candidate addresses asserted to differ |
| `0xfc302e` | `Keytbl` (XBIOS $10, `src/xbios/keytbl.c`) | 18 | 12 / 224 install | **0.99** (16 / 222) | ✅ verified | seven install/keep combinations over three INDEPENDENT arguments (the shape Kbrate does not have), each field read back from the oracle's ledger and each skip asserted as a non-write; `tst.l`/`bmi` only — 0 and $7fffffff install, every bit-31 pointer keeps; the struct address as a constant result |
| `0xfc15f8` | `Protobt` (XBIOS $12, `src/xbios/protobt.c`) | 41 | 2283 / 34224 format, 2328 / 35026 random serial | **0.23** format (954 / 8066), **0.25** random serial (990 / 8638) | ✅ verified | the 255-word final sum against the 256-word probe (two deliberately different loop lengths); the non-executable sector missing $1234 by exactly one; the three-byte serial low byte first with the frame slot read back from the ORACLE's ledger; a serial above $ffffff replaced through a real call into `Random`, over four ticks; the four BPB prototypes, a negative type, type 4 past the table, and disk type 1725 whose `muls.w #19` = `$8007` reads BELOW the table; the whole-Format composition; the buffer wherever the caller points |
| `0xfc4698` | `Cursconf` (XBIOS $15, `src/xbios/cursconf.c`) | 30 | 10 / 144 blink, 11 / 144 get rate, 132 / 1318 hide, 143 / 1448 show | **1.65** blink, **1.33** get rate, **1.37** hide, **1.47** show | ✅ verified | the six RAM arms plus the out-of-range return, each at its truncation boundaries (the two that DRAW are the sentence at the end of this cell); what each arm leaves in D0 read OUT OF THE ROM's jump table rather than written down ($0010/$0016/$001c for the arms that set no result); the rate and the spare proved to be different bytes; and the WIDTH — the caller's high half surviving the `move.w` arms and cleared by the `moveq #0,d0` ones. Arms 0/1 are the console's own cursor renderer and no longer halt: they call `console_hide_cursor`/`console_show_cursor` ($fc45d8/$fc45be), and `test_bios_vt52.py` drives each over both a cursor that is on screen and one that is not, with the dispatch's displacement still the result. |
| `0xfc305a` | `Bioskeys` (XBIOS $18, `src/xbios/keytbl.c`) | 6 | 5 / 128 | **1.18** (6 / 144; accepted: image pointer) | ✅ verified | the three ROM tables identified independently by the keyboard row each spells at scancode $10; installed over three staged tables; each field cleared separately (three stores, not one copy); and all three stored even when already correct, attributed by the poison pass. `void`: the routine sets no result |
| `0xfc309a` | `Kbrate` (XBIOS $23, `src/xbios/kbrate.c`) | 16 | 5 / 90 read, 11 / 156 write | **1.80** read (9 / 130), **1.28** write (13 / 188; accepted: image pointer) | ✅ verified | the pair reported as one word in the ROM's order; six pairs storing both low bytes; a negative repeat leaving its byte alone; the COUPLING — three negative-delay pairs (incl. `$ff80`, whose low byte looks positive) skipping BOTH stores; the caller's high half of D0 surviving; and storing the pair already held |
| `0xfc097e` | `Supexec` (XBIOS $26, `src/xbios/supexec.c`) | 11 | 5 / 92 | **1.00** (5 / 92), both cases | ✅ verified | five results passed through untouched; the staged routine's writes passing through; a bare `rts` leaving the caller's D0 alone; the routine run being the one 4(sp) names, with a DECOY staged at a fixed address on both sides. The stack-frame claim (`jmp` not `jsr`) is the ORACLE's alone off target; on target the body IS the `jmp`, and Tier 3's second differential pins it once this has a bench row |
| `0xfc0a92` | `Physbase` (XBIOS $02, `src/xbios/physbase.c`) | 23 | 7 / 138 | **1.12** (7 / 150; accepted: the byte widening) | ✅ verified | eight declared register pairs incl. the two halves alone, $800000 and $ffff00; the ordered I/O read ledger compared on every case so the ORDER of the two registers is a claim; the low eight bits asserted absent; a 512-value host-side sweep; decoys at $ff8201/$ff8203; half a declaration refused BY THE MISSING BYTE both ways. Mutation 3/3 |
| `0xfc0ab8` | `Setscreen` (XBIOS $05, `src/xbios/setscreen.c`) |  21 | 11 / 202 both bases, 8 / 130 keep everything |  **1.28** both bases (19 / 248; accepted: (A)+(G)+(D)), **1.24** keep everything (11 / 152; accepted: (A)+(D)) | ✅ verified | two of three arms: four logical bases incl. the one already held and $7fffffff; four physical bases through the hardware WRITE ledger incl. $12345678 proving bits 31..24 and 7..0 are DROPPED not rounded; the sign boundary on both; INDEPENDENCE as three calls; the all-keep call doing nothing; the caller's whole D0 given back on both arms. The RESOLUTION arm HALTS (`recreate_not_reconstructed`): it ends in `jsr $fca914`, the console re-init, pinned from the ROM's own bytes. Mutation 4/4 |
| `0xfc0b06` | `Setpalette` (XBIOS $06, `src/xbios/palette.c`) |  11 | 3 / 84 |  **1.73** (5 / 116; accepted: image pointer + the caller's D0) | ✅ verified | THE ABSENT `tst`/`bmi`: five pointers incl. $ffffffff and $80000000 all stored; 0 over the snapshot's own 0 attributed by the poison pass; the whole effect asserted to be four bytes and no hardware store — the palette itself is the VBL's; the caller's whole D0 given back. Mutation 3/3 |
| `0xfc0b0e` | `Setcolor` (XBIOS $07, `src/xbios/palette.c`) |  46 | 10 / 140 read, 11 / 160 write | **1.28** read (14 / 168), **1.18** write (15 / 182; accepted: the caller's D0 as an argument, the palette base as an immediate) | ✅ verified | all sixteen registers against a declared row with a distinct word each; five wrapping index arguments incl. 16, 24, $8000, $ffff with no bounds test; the reporting mask at four boundaries; twelve store cases proving the value reaches the register UNMASKED; the read BEFORE the `bmi`; the caller's high half surviving; a decoy at $ff8240; one byte of the word declared refusing. Mutation 4/5 (the fifth EQUIVALENT: the five-bit mask discards every bit the `add.w` wrap could move) |
| `0xfc07d0` | `Vsync` (XBIOS $25, `src/xbios/vsync.c`) |  26 | 8 / 156 one spin, 14 / 252 four spins | **0.97** one spin (9 / 152), **0.92** four spins (15 / 236) — both PINNED, incl. the IPL bracket | ✅ verified | THE FIRST RECONSTRUCTION HERE THAT DOES NOT TERMINATE ON ITS OWN, driven by Phase 8's scheduled write: Tier 1 at the spin's own `cmp.l` ($fc07dc) over four arrival counts, each equal to the oracle's arrivals AND the candidate's polls site by site; the result the clock sampled BEFORE the wait; five entry clocks proving a whole-LONGWORD compare; a clock going BACKWARDS still ending the wait (`cmp`/`beq` is a difference test); the two negative controls running the ORIGINAL to the cap. Tier 3 through the READ TRIGGER on `_frclock` itself, which is the only trigger both oracle doors can fire (a PC inside the m68k build moves with every recompile), at TWO arrival counts, with the two runs' reads of $466 compared; the offset between the two triggers pinned by running one blank through each. Both ratios PINNED because the `ipl.h` bracket is the routine's TERMINATION and is invisible to Tier 1 — deleting it leaves all 26 cases green and moves these rows to 0.64x/0.75x. Mutation 4/4 (a target-only double read caught at an ODD spin count by the read comparison alone; a build that never spins caught as `never came due`; the trigger off by one caught by the ORIGINAL's own loop and by the two-trigger pin; the bracket deleted caught by both pins) |
| `0xfc2f02` | `Offgibit` (XBIOS $1d, `src/xbios/gibit.c`) | 22 | 45 / 664 |  **0.90** (48 / 604) — incl. the OUTER IPL bracket | ✅ verified | THE ARGUMENT IS THE MASK TO KEEP: eight single-bit clears (TOS's own $ef among them), both ends, $55/$aa; the pair asserted to DISAGREE over one mask; four words proving only the low byte is read; the write made even when nothing changes; register 14 against a distinct-byte entry file; the internal entry at $fc2ed8 pinned. Mutation 3/3 |
| `0xfc2edc` | `Ongibit` (XBIOS $1e, `src/xbios/gibit.c`) | 22 | 45 / 664 |  **0.90** (48 / 604) — incl. the OUTER IPL bracket | ✅ verified | composed over the verified `Giaccess`: the witness is the chip's ordered ledger READ 14 / WRITE 14 / READ 14; eleven masks incl. every single bit, one already set, $ff and 0; the high byte never read; the write unconditional; the caller's whole D0 given back. Mutation 4/4 |
| `0xfc3074` | `Dosound` (XBIOS $20, `src/xbios/sound.c`) | 21 | 7 / 128 play, 5 / 98 report only | **1.23** play (9 / 148), **1.34** report only (7 / 118; accepted: image pointer) | ✅ verified | THE `clr.b $0e8e` handshake over a driver 42 ticks into a list, incl. when the countdown is already zero (poison-attributed) and NOT cleared on the report-only arm; four cursors incl. 0 and the one already held; three negative pointers; the OLD cursor as a whole longword. The 200 Hz driver is the timer C handler's. Mutation 3/3 |
| `0xfc3088` | `Setprt` (XBIOS $21, `src/xbios/sound.c`) | 15 | 6 / 108 write, 5 / 90 report only | **1.59** write (10 / 148), **1.80** report only (9 / 130; accepted: image pointer + the caller's D0) | ✅ verified | stored as a WORD not a byte; three negative arguments incl. $ff80 at the ROM's width; the OLD word reported; the caller's high half surviving on both arms. Mutation 3/3 |
| `0xfc2682` | `Jdisint` (XBIOS $1a, `src/xbios/mfp.c`) | 79 | 39 / 514 |  **0.61** (23 / 328) | ✅ verified | all sixteen channels over both halves of all four register pairs with a DISTINCT declared byte per register; the ORDER (mask, enable, pending, in-service) out of the hardware write ledger; the read half of every `bclr` ledgered (four declared bytes incl. $00/$ff prove the five preserved bits); five aliased arguments pinning `andi.l #15`; an undeclared register refuses by name; the masked channel returned in D0 (the ROM's andi.l precedes the movem push). Mutation 5/5 |
| `0xfc26bc` | `Jenabint` (XBIOS $1b, `src/xbios/mfp.c`) | 79 | 23 / 346 |  **0.50** (16 / 194) | ✅ verified | the same sixteen channels in the OTHER order — arm then unmask — and the same declared-read arithmetic; also the code `Mfpint`'s enable half IS, decoded out of the ROM's own `bsr` |
| `0xfc2658` | `Mfpint` (XBIOS $0d, `src/xbios/mfp.c`) | 88 | 70 / 1024 | **0.56** (46 / 588) | ✅ verified | THE WHOLE ROUTINE, where this row read a slice: the disable, the vector at `$100 + channel * 4` and the enable over all sixteen channels as ONE ordered stream. The enable half is now SERVED the bytes the disable half wrote (the declared map's write-through arm) and is asserted as THOSE bytes rather than through the model; the mask and the masked channel returned over five aliased arguments; four held bytes over the whole composition. Mutation: covered by the timer programmer's sweep below |
| `0xfc25b0` | MFP timer programmer (`src/xbios/xbtimer.c`) | 57 | 84 / 1072 | — | ⚠️ verified, unpriced | verified WHOLE rather than as its five clears — all four timers × both control/divider pairs: the masked clears, the data register written and read back, and the control bits ORed into the byte the clear left. UNPRICED because its arguments are D0/D1/D2 and `tier3.CALL` spells frame arguments and `ENTRY_D0` only; its cost is measured inside the `Xbtimer` and `Rsconf` rows instead. Mutation 8/8: the mutant that drops the MFP base aims the write-and-verify spin at an undeclared address, which used to HANG pytest rather than red. The off-target build now caps the loop at `MFP_VERIFY_PASSES` and ends it in `os_refused(0)`, so that mutant reds through `_vet_no_os_refusal` (43 cases across this row and `Rsconf`'s); the TARGET build keeps the ROM's own unbounded spin, and on a correct run the ledger is one store and one read either way |
| `0xfc2ff2` | `Xbtimer` (XBIOS $1f, `src/xbios/xbtimer.c`) | 57 | 166 / 2198 install, 94 / 1180 no vector | **0.68** install (130 / 1516), **0.78** no vector (83 / 924) | ✅ verified | the programmer, the channel table `$fc302a` and `Mfpint`'s own body end to end for all four timers, where this row read HALTS; and the negative-vector arm, which programs the timer and installs nothing. The RAW-byte and out-of-range shapes stay candidate-only — a timer past the table would program a register that is not a timer: the `bsr` lands PAST Mfpint's `andi.l #15`, so timer 4's $4a reaches slot $228 and a byte ≥ $80 takes register B by the SIGNED half-select |
| `0xfc290e` | `Rsconf` (XBIOS $0f, `src/xbios/rsconf.c`) | 32 | 19 / 260 report, 23 / 332 store four, 116 / 1436 baud | **2.03** report, **1.72** store four, **1.11** baud (accepted: `movep.l` has no C form; on the baud arm that mechanism is diluted by the timer programmer) | ✅ verified | the result read BEFORE anything changes and packed UCR:RSR:TSR:UDR from four DIFFERENT declared bytes; each optional register on its own and all four in the ROM's order; five words separating `tst.w` from `tst.b`; the handshake byte over eight values incl. mode 3 demoted to XON/XOFF. The BAUD arm no longer halts: four rates, the two baud tables indexed out of the ROM, the RSR/TSR bracket that stops the receiver and the transmitter across the rate change, and the caller's own four registers applied after it. Mutation 4/4 |
| `0xfc2212` | `Ikbdws` (XBIOS $19, `src/xbios/acia.c`) | 21 | 5731 / 84016 (two bytes) |  **1.00** (5734 / 84034; pinned: the settle loop is the ROM's own `dbf` shape on target, a FLOOR the 6301 is owed) | ✅ verified | five byte strings whose order and repeats are separable; `count + 1` at counts 0..2; two buffers a page apart; one TDRE poll per byte in the named-slot stream with the MIDI stream empty. Shrinking the settle loop leaves every Tier 1 case green and reddens the pinned row (measured); the count is pinned to about ±38 passes by the ratio, stated as a floor. Mutation 3/3 |
| `0xfc2030` | `Midiws` (XBIOS $0c, `src/xbios/acia.c`) | 21 | 23 / 304 |  **0.90** (22 / 278) | ✅ verified | the same cases on the other ACIA, whose status comes through the DECLARED map where the IKBD's comes through the named set — each routine's polls in its own stream; and the pair saying what a per-run constant cannot: undeclared, or declared not-ready, the ROM's loop never leaves |
| `0xfc30bc` | `Kbdvbase` (XBIOS $22, `src/xbios/kbdvbase.c`) | 8 | 3 / 68 | **1.00** | ✅ verified | the address proved three ways: every named slot of the block holds an installed ROM handler, the table fits below the keyboard struct, a scrambled table changes nothing (`move.l #`, not a load); plus the WIDTH, a caller's marked high half not surviving |
| `0xfc2f28` | `Initmous` (XBIOS $00, `src/xbios/initmous.c`) | 27 | 2869 / 42064 disable, 48709 / 713890 absolute |  **1.00** disable, **1.00** absolute | ✅ verified | from the DISASSEMBLY (a decompile failure): all five modes' packets built independently and compared as the bytes SENT and LEFT at `$e6e`; each mode's `Ikbdws` count one less than its packet; mode 0's single byte and its ROM `rts` handler; five unknown modes installing the caller's handler and THEN refusing — the ROM's order; six topmodes pinning `16 - topmode` as a BYTE subtract; the block read from wherever the caller points; the send-vs-store order of mode 0 is unpinned (no cross-stream order). Mutation 4/4 |

## Verified — bios (20)

The BIOS wave's first set: the trap #13 leaves that read and write RAM only. `Bcostat`'s and
`Bconout`'s whole tables are reconstructed, and with `Bconout` the VT52 CONSOLE and the ACIA INPUT
CHAIN behind the IKBD handler (wave 6); what still halts is the two `Bconin` drivers that WAIT, and both
are DEFERRALS rather than limits — `PRT:` a declared GPIP list away, `AUX:` a staged input ring away. Every unreconstructed arm HALTS on both builds
(`recreate_not_reconstructed`: abort on the host, `trap #7` on the 68000) rather than returning a
plausible value. The four interrupt vectors' ENTRY sequences are `src/bios/isr.S` (44 of 48 literal words
byte-identical to the ROM, the four excused words each asserted to differ), proved by the transcription
differential; the C cores stay as the bodies' own Tier 1 instrument, so each handler carries two rows.

| Addr (ROM) | Name | Cases | Cost (insns / cycles) | Tier 3 (recreate / original) | Status | Verification |
|---|---|---|---|---|---|---|
| `0xfc0a46` | `Getmpb` (BIOS $00, `src/bios/getmpb.c`) | 13 | 13 / 254 |  **1.14** (14 / 284; the LEAF RULE admits it: +30 cycles, mechanism A) | ✅ verified | both structures out of the oracle's write ledger; the descriptor rebuilt from `_membot`/`_memtop` over five TPAs incl. equal and INVERTED bounds (the `sub.l` is unchecked); the MPB written wherever the caller points; a second call rebuilding the first's descriptor; and the ORDER — an MPB laid at `_membot - 8` so `mp_rover` overwrites `_membot` before the routine reads it, which reds a hoisted read; memtop - membot returned in D0. Poison on every case |
| `0xfc0984` | `Bconstat` (BIOS $01, `src/bios/bcon.c`) | 29 | 15 / 178 empty, 14 / 176 ready, 8 / 126 no driver | **1.26** ring empty, **1.29** ring ready, **1.88** no driver (accepted: the driver dispatch is a compare chain vs the ROM's `jmp (a0)`) | ✅ verified | the table walk AND the driver it jumps into, per device: the snapshot's own drained rings; a head/tail sweep on the console's copy plus a pair on each of the other two (three separate ROM copies); equal head/tail whatever they hold; one ring filled at a time so a driver naming the wrong ring diverges; the five no-driver devices returning the dispatch's scratch through a marked D0; `lsl.w #2` proved by device `$4002` |
| `0xfc098c` | `Bconin` (BIOS $02, `src/bios/bcon.c`) | 30 | 30 / 376 console, 31 / 384 MIDI | **1.18** console, **1.16** MIDI (accepted: dispatch) | ✅ verified | the console's four-byte record and MIDI's one-byte one, each with its own head advance and its wrap-to-zero at the ring's size; MIDI's `$ffffff00 \| byte` over seven bytes; the two drivers reading their own ring; and the STORE ORDER — a ring whose buffer is pointed at itself, so the record read is the ring's own size and head words before the store changes them. Blocking is the ROM's real spin on both builds (a case stages the record; an empty ring runs the original to the oracle's cap) |
| `0xfc0994` | `Bcostat` (BIOS $08, `src/bios/bcon.c`) | 21 | 9 / 130 console, 12 / 168 printer, 18 / 236 rs232, 12 / 166 ikbd, 12 / 166 midi | **1.84** console (17 / 206; accepted: (B) dispatch, over a driver whose whole body is `moveq #-1,d0` — the chain IS the routine), **1.55** printer (19 / 238; accepted: (B)), **0.88** rs232 (19 / 212), **1.46** ikbd (18 / 224; accepted: (B)), **1.44** midi (18 / 222; accepted: (B)) | ✅ verified | the console's `moveq #-1,d0` reached for device 2 and only device 2; the three no-driver devices; `lsl.w #2` — and the WHOLE table is now in reach. The console's constant; the printer's MFP GPIP bit 0 (a BUSY line, so the branch reads the opposite way round to the answer) and both 6850s' TDRE, each swept over both sides of its own bit with every other bit inverted, and each read pinned in the ordered stream — `hw_events` for the two named slots, `io_events` for MIDI's `$fffc04`, one `io_seed` door. And the RS232's, which reads NO hardware at all: its output ring's tail advanced one record and compared with the head, with the ROM's wrap-at-size (not modulo) pinned at both boundaries. Mutation 4/4 |
| `0xfc099c` | `Bconout` (BIOS $03, `src/bios/bcon.c` + `src/bios/vt52.c` + `src/bios/conout_glyph.c`) | 243 | 13 / 182 midi, 2867 / 42038 ikbd, 213 / 2962 printer, 15 / 234 printer held off, 25 / 342 rs232 ring only, 58 / 762 rs232 primed, 7 / 116 no driver, 235 / 2308 console glyph, 357 / 3492 console glyph with the cursor, 61 / 756 console line feed, 10284 / 180834 console scroll, 14006 / 166532 console clear to end of screen, 19 / 252 console escape state, 231 / 2260 raw console | **1.01** ikbd, **1.03** console scroll (pinned UNDER the bar), **1.04** printer, **1.44** rs232 primed, **1.49** console clear to end of screen, **1.71** console glyph with the cursor, **1.85** raw console, **1.88** printer held off, **1.90** rs232 ring only, **1.93** console glyph, **2.24** console line feed, **2.76** midi, **3.27** console escape state, **3.63** no driver (the rest accepted; see `bench/tier3.py`) | ✅ verified | the table walk AND every driver it jumps into. The two 6850 senders: the low byte of the character word on each data port, the poll as a DECLARED SEQUENCE (busy, then ready) in the ordered stream, and the dispatch's own scratch back in D0 — the same answer a device with no driver gives. The printer: the whole YM2149 send as an ordered chip ledger (mixer read, port B turned into an output, the byte, then the strobe LOW TWICE and HIGH, each a `Giaccess` read-modify-write), the BUSY wait round a declared sequence, the five-second hold-off's UNSIGNED compare proved by a failure stamp AHEAD of the clock, the thirty-second timeout reached through a SCHEDULED 200 Hz tick at its exact boundary and one tick short, its `blt` proved SIGNED by a clock half the longword range on — and the SERIAL REDIRECT, which is a BYTE test on a WORD field and so reads bit 12: `$0010` prints and `$1000` redirects. The RS232: the byte into the output ring at the ADVANCED tail with the ROM's wrap-at-size at both boundaries, a busy transmitter left alone, an idle one handed the byte straight back out of the ring, the flow-control pair ANDed over four combinations, an XON jumping the queue and being cleared, and three layers of D0 — the caller's high half, the character's high byte and the flow byte's low one. The console: the six-state machine at $4a8 (normal, escape, ESC Y row/column, ESC b, ESC c), the control codes $07..$0d (BEL trap-free through conterm bit 2 and the $fc31c2 sound list; VT and FF the same table entry as LF), every escape the ROM's three jump tables really implement (A B C D E H I J K L M Y b c d e f j k l o p q v w; F G g h i m n r s t u are table entries pointing at a bare rts), the cursor lock as a DEPTH whose unlock leaves the depth in D0 (so `ESC l` puts the cursor in column `depth`, swept at four depths), the horizontal/vertical escapes' differing D0, the spare byte $2995 that is not spare, the four screen routines reached through RAM vectors (CPU set reconstructed; the blitter set halts), a group being `1 << (planes >> 1)` words for the clear and `planes` for the glyph. Mutation 21/21 |
| `0xfc0a72` | `Setexc` (BIOS $05, `src/bios/setexc.c`) | 29 | 9 / 134 read, 10 / 144 install | **1.06** read, **1.06** install | ✅ verified | reconstructed from the DISASSEMBLY (one of COMPONENTS.md's 73 decompile failures): five OS vectors read back and asserted to be ROM addresses; every handler with bit 31 set a read; nine slots installed incl. vector 0; no bounds check ($400..$7ffc); the WORD index wrapping ($4000 is vector 0); and every slot the battery reaches declared as `CASE_SPANS` so the snapshot's mask is checked against them. Poison on every case |
| `0xfc0a8a` | `Tickcal` (BIOS $06, `src/bios/sysvars.c`) | 5 | 4 / 74 | **1.41** (5 / 88; accepted: image pointer) | ✅ verified | the snapshot's own calibration; the word read at the three boundaries a byte read or a sign-extending one would fail; the `clr.l` pinned against a caller that entered with a dirty D0 |
| `0xfc0a2e` | `Drvmap` (BIOS $0a, `src/bios/sysvars.c`) | 8 | 3 / 72 | **1.50** (4 / 88; +16 cyc = the image-pointer load, accepted) | ✅ verified | the snapshot's A:+B:; seven bitmaps separating a longword read from a word or a byte |
| `0xfc0a34` | `Kbshift` (BIOS $0b, `src/bios/kbshift.c`) | 21 | 6 / 94 read, 7 / 104 write | **1.48** read, **1.53** write (accepted: image pointer) | ✅ verified | the `bmi` on the WORD ($ff80 reads, $0080 STORES); the old state zero-extended over seven bytes; seven modes storing their low byte ($7fff stores $ff); and storing the value already held, attributed by the poison pass |
| `0xfc07f2` | `trap #14` XBIOS entry (`src/bios/trap.S`, `xbios_trap14`) | 34 | 35 / 652 with Logbase (incl. the 7 / 106 staged caller) | **1.01** (35 / 656; +4 cycles: the ROM's `lea (d16,pc)` is absolute long here) | ✅ verified | The second of the dispatcher's two exception entries, six bytes above `$fc07f8`: `lea XBIOS_FUNCTION_TABLE(pc),a0` and a `bra.s` into the shared body — the only thing the two traps differ in, proved by `test_each_entry_indexes_its_own_table`. Same transcription differential as the row below, plus a BYTE PIN of the whole $fc07f2..$fc0845 span against the ROM with only the three link-forced encodings spliced (two `lea`s → absolute long, and the `bra.s` displacement they move) — which is what refuses a `bge.s` transcribed as `bcc.s`, invisible to every other check. 34-test battery shared with the row below |
| `0xfc07f8` | `trap #13` / `trap #14` dispatcher (`src/bios/trap.S`) | 34 | 26 / 548 dispatcher alone, 34 / 642 with Drvmap (incl. the 7 / 106 staged caller) | **1.01** every case (+4 cycles: the ROM's `lea (d16,pc)` is absolute long here) | ✅ verified | ASSEMBLY, not C — an exception handler, proved by the transcription differential (`RomBench.measure_transcription`): both sides entered with the same whole register file and the whole of D0-D7/A0-A6 required back. The hand-built frame pinned against a real `trap` (only the saved return PC differs); the save-area frame's depth and layout; A5 = 0 read from inside the call; the register contract incl. the d1/d2/a0/a2 pass-through and a1 coming back as savptr; an out-of-range number returning `caller_high \| fn`; the INDIRECT (bit 31) entry through `hdv_rw`; the `move.l usp,sp` arm. 8/8 mutants killed. A whole `Bios(10)` call is 496 cycles, 93.5 % of it this dispatcher |
| `0xfc06c8` | `isr_hbl` (vector $68, `src/bios/hbl.c`) | 18 | 8 / 126 level zero, 7 / 108 already masked |  **1.09** level zero, **1.18** already masked (accepted: (A), plus the frame address as a second argument); ISR ENTRY (`src/bios/isr.S`): **0.98** level zero, **0.97** already masked | ✅ verified | every masked level 1-7 left alone and six level-0 frames or-ed incl. `$f8ff`; the saved D0 given back; the vector table read out of the snapshot. THE ONLY HANDLER WHOSE FRAME IS IN COMPARED IMAGE (`test/isr.py`'s `STAGED_FRAME`). Mutation 3/3, +1 on the entry stub |
| `0xfc06de` | `isr_vbl` (vector $70, `src/bios/vbl.c`) | 82 | 38 / 776 quiet, 147 / 2102 full frame, 2048 / 20910 monitor change, 6 / 138 semaphore taken |  **1.00** monitor change (pinned), **0.97** quiet (pinned: (I)), **1.14** everything queued (accepted), **1.27** semaphore taken (accepted: (A)); ISR ENTRY: **1.01** monitor change (pinned), **1.00** semaphore taken, **1.23** quiet (accepted), **1.23** everything queued (accepted) | ✅ verified | both clocks against the semaphore's sign boundary; the release RE-READ, proved by a queue routine storing its own semaphore; the monitor follower over four resolutions × both monitors × eight `defshiftmd` values incl. the signed keep-arm; sixteen palette words as an ordered hardware-write stream and `colorptr` cleared; six screen bases MID-then-HIGH with `screenpt` NOT cleared; the cursor blink's four arms over six cell geometries; the queue walked exactly `nvbls` slots; the dump hook with a decoy. `flock` set on every case: the floppy VBL past that gate HALTS. Mutation 10/11 (the eleventh EQUIVALENT: a `bset` over a bit already set writes the byte that is already there — no image, ledger or cycle surface separates it), +4/4 on the entry stub; the cursor's ZERO-count arm is exercised and its pass count unpinned (the battery says why) |
| `0xfc30c4` | `isr_timer_c` (vector $114, `src/bios/timerc.c`) | 88 | 6 / 142 divided away, 58 / 1018 serviced |  **1.18** divided away (accepted: (A)+(H)), **1.08** serviced (pinned); ISR ENTRY: **1.00** divided away, **1.33** serviced (accepted: (H)+(L)) | ✅ verified | the divider as a ROTATE over seven words; the tick counted and the channel acknowledged on BOTH paths; the acknowledgement a function of five declared `$fffa11` bytes; the whole Dosound interpreter — five register writes, the mixer's read-modify-write over six declared chip states, `$80`, both `$81` arms, every pause from `$82` to `$ff` incl. the zero that ends the list, a paused driver resuming; the auto-repeat's `conterm` gate and both countdowns to their last tick. The INJECTION at `$fc2c42` is `kbd_queue_key` now (`src/bios/keyboard.c`): three cases drive the last tick of the interval, over three different held scancodes, so the reload from `Kbrate`'s byte and the record the held key leaves in the IOREC are both pinned — the arm that used to halt. Mutation 8/8, +3/3 on the entry stub |
| `0xfc29ce` | `isr_acia` (vector $118, `src/bios/ikbd.c`) | 30 | 16 / 424 one pass, 26 / 590 two passes, 114 / 1580 real vectors + a keystroke, 182 / 2528 real vectors + a mouse packet |  **1.11** one pass (pinned: (K)), **1.10** two passes (pinned: (K)), **1.03** both real-vector cases; ISR ENTRY: **1.71** one pass, **1.52** two passes, **1.12** a mouse packet, **1.18** a keystroke (all accepted: (H)+(L)+(K)) | ✅ verified | both KBDVECS routines called once each in the ROM's order, each from its own slot with a decoy; the loop ended on GPIP bit 4 ALONE over four bytes differing everywhere else; the channel acknowledged with the other seven bits kept; the `movem.l d0-d3/a0-a3/a5` list read at its edge. The two ROM service routines ($fc29fc/$fc2a0c) are STAGED OVER; the snapshot pinned to still hold them — and the TWO-PASS entry, which a DECLARED SEQUENCE made a case (`io_seed={MFP_GPIP: [asserted, idle]}`, TRAP_MODEL Phase 16): both service routines called again in the ROM's order with both KBDVECS vectors re-read, the channel acknowledged ONCE however many passes, the two GPIP reads compared in order in the named set's stream while the declared map's stays empty. A declaration that never says IDLE — a constant or a list that runs out — spins to the oracle's cap, both driven. TWO CASE SHAPES NOW. The staged shape isolates the handler as before. The REAL-VECTOR shape leaves the captured machine's own `$fc29fc`/`$fc2a0c` in KBDVECS and declares the two 6850s instead, so a three-byte relative-mouse report is assembled over THREE passes of the loop — a `[asserted, asserted, idle]` list on `$fffa01` and a three-byte list on `$fffc02`, which is the first case in this project to need two declared SEQUENCES at once — and a keystroke reaches the IKBD IOREC through the whole chain. A decoy in `midisys`' place is still answered, so the routines are inputs and not calls by name. Mutation 4/4, +2/2 on the entry stub, +2/2 this wave; the A5-pin mutation is a cycle surface only (see (K)) |
| `0xfc29fc` | `midi_acia_service` (KBDVECS `midisys`, `src/bios/acia_service.c`) | 20 | 23 / 362 a byte | **1.40** a byte (accepted: (A)+(L) — the vector call's clobber list over a body that is a status read, a data read and that call) | ✅ verified | the shared body's four status arms over both entries — bit 7 clear with every OTHER bit set, and bit 7 set with bits 1–4 set but 0 and 5 clear, so neither test can be the whole byte; the data port left UNDECLARED on those four, so a read the model does not serve refuses by address; the OVERRUN arm's own read; and the case THE SEQUENCE MODEL EXISTS FOR — a byte AND an overrun on one entry, which pops `$fffc06` twice and is a list of two, compared as an ordered stream. The error vector read BEFORE the status byte, proved by having the byte's own vector rewrite the slot mid-run. Five bytes through `midivec` incl. both ends of the header range (a MIDI byte is never a packet). The whole path composed with the ROM's own `$fc2e3a` in the slot, which is what pins A0 |
| `0xfc2a0c` | `ikbd_acia_service` (KBDVECS `ikbdsys`, same file) | 71 | 48 / 658 a packet's last byte | **1.75** a packet's last byte (accepted: (A)+(L)+(M), two vector calls) | ✅ verified | all ten packet headers against the ROM's two tables, read out of the image rather than written down; the two SIGNED ranges that keep a header ($f8–$fb at `$e44`, $fd–$ff at `$e4d`) and the three that keep none; the five tabled kinds' fill at `end - remaining` at two counts each; the dispatch on the byte that zeroes the count, with the packet address read out of the descriptor and the vector out of the KBDVECS SLOT the descriptor names; the packet passed BOTH pushed and in A0, compared as one address; the state byte cleared AFTER the handler runs, proved by a stub that reports what it finds; kinds 2 and 3 sharing `mousevec` so only the address tells them apart; the two single-stick reports at `$e4e + kind - 6` with `joyvec` handed the header; the `$fd` report overwriting its own header; four bytes below `$f6` handed to the keyboard; and both negative controls — an undeclared port refused by address, a spent list refused by address and READ INDEX |
| `0xfc2a42` | `acia_take_byte` (same file) | 91 (all of the two rows above enter through it) | 21 / 276 a header | — | ⚠️ verified, unpriced | `cmpa.l #$c76,a0` is the whole discriminant: every case above reaches it, and a byte filed under the wrong IOREC leaves through `midivec` instead of the keyboard. DEFERRED rather than unpriceable — the five routines either side of it are priced now; what this one still has not got is a case that enters it DIRECTLY, so nothing pins the registers its callers leave it (`A0` = the IOREC, `A1` = the 6850) and a Tier 3 row built on a guessed contract would be a number about a call the machine never makes |
| `0xfc2e3a` | `midi_queue_byte` (the ROM's own `midivec`, same file) | 8 | 11 / 156 | **1.53** one byte into the ring (accepted: (A)+(M) alone — the cleanest measurement of the register-argument marshalling in the table) | ✅ verified | the one-byte record at four tails; the wrap AT the size and not one short of it, at both boundaries; a full ring at three head/tail pairs incl. the wrap, leaving the record and BOTH indices alone — the newest byte is the one that is lost |
| `0xfc2b5c` | `kbd_scancode` (`src/bios/keyboard.c`) | 26 | 70 / 842 a key | **1.61** a key (accepted: (A)+(M), plus the ROM's FALL-THROUGH into `$fc2c42` where the C makes a call of it) | ✅ verified | the eight modifier arms from a clear byte and from every bit set, so an arm that cleared the byte or set the wrong bit diverges; CapsLock as a `bchg` from three states, and its RELEASE proved NOT to be in the chain; the click on the same `conterm` bit as the key path's; a make arming the repeat from `Kbrate`'s own bytes; a second key zeroing both countdowns and LEAVING the held scancode; a break disarming and queueing nothing; and the two breaks ALT turns into mouse-button releases, with and without ALT |
| `0xfc2c42` | `kbd_queue_key` (same file; TIMER C's auto-repeat calls it too) | 88 (+3 from `$fc30c4`) | 43 / 560 a key | **1.85** a key (accepted: (A)+(M) over the table reads and the ring put) | ✅ verified | five keys through each of the three `Keytbl` tables with the ASCII read out of the table the snapshot's pointers name; SHIFT overriding CapsLock and not the reverse; all ten shifted F-keys, the keys either side of the run, and the test proved to be on the MASKED scancode; CONTROL's mask, its three named characters, its CR→LF (which survives the three scancode arms) and its three renumbered keys; ALTERNATE's screen dump as a WORD increment; the four mouse-button codes read out of the ROM's own table, each moving its own kbshift bit and sending a packet whose header is what it just wrote; the four arrows at both step sizes; the whole number row renumbered by a BYTE add; every letter's ASCII dropped, tested on the ASCII; `conterm` bit 3 over three shift states; the ring at four tails, both wrap boundaries and three full-ring pairs; the click made BEFORE the ring is looked at; and the ring being the one A0 names |

## Verified — gemdos (105)

GEMDOS waves 1 and 2, seven groups: the `trap #1` ENTRY and the dispatcher behind it, the RAM-only
LEAVES, the CHARACTER DEVICES and the MEMORY MANAGER (wave 1 — `src/gemdos/trap1.S`, `dispatch.c`,
`leaves.c`, `console.c`, `memory.c`), then the FILE SYSTEM over a staged RAM disk and the PROCESS
group with the handle machinery under it (wave 2 — `fs_disk.c`, `fs_name.c`, `process.c`,
`handles.c`). Each row is one function of the ORIGINAL ROM, entered at its
own address over the post-boot snapshot and compared byte-for-byte (`../README.md`, Tier 1); the
trap entry's own row is the TRANSCRIPTION differential instead, as `src/bios/trap.S`'s rows are, and
the dispatcher carries two rows because its arms past the termination record can only be entered as
a SLICE (`test/gemdos.py`, `ROUTINE_OF_TRAMPOLINE`) — as does `Pexec`, one routine along, through a
trampoline of its own (`test/gemdos_process.py`).

THREE ROWS ARE ⚠️ VERIFIED AND UNPRICED, and it is the same fact about all three: `Pterm`, `Pterm0`
and `Ptermres` do not return. Their differential stops at a CHECKPOINT — the `jsr` into the trap
entry's epilogue — and Tier 3 runs both columns to the routine's own `rts`, which there is none of,
so the registry carries them with an eighth field (`stop_pc`) and `bench/tier3.py` lists them under
the table rather than pricing them. Their cost column is the ORACLE's own, to that checkpoint.

WHAT A CHECKPOINT CANNOT SEE is the other side of that `jsr`. The host build RETURNS the exit code
where the target build jumps, and the ORIGINAL is stopped before it jumps, so nothing in these rows
or in any case executes `gemdos_trap1_epilogue` — including the D0 the epilogue re-stores as the
parent's result. It is pinned by construction (`src/gemdos/process.c`) and by no surface; the surface
that would close it is named in `## Not reconstructed, and why`.

Ratios run from 0.38x to 1.75x and every priced row is under the bar or carries a written
acceptance. THE TARGET BUILD TAKES THE ROM'S OWN
`trap #13` wherever the ROM reaches the BIOS through `gemdos_bios_trampoline` ($fc4eac), so both
columns of a character-device row carry the trap, the BIOS dispatcher and the driver, and what the
ratio compares is the GEMDOS layer itself (`src/gemdos/console.c`, `include/bios/bcon.h`). The HOST build
calls the BIOS core directly — there is no 68000 to take a trap — and that is the stand-in ROM mode
asks for rather than a decision about the routine; the register-save frame the oracle's trap leaves
below `savptr` is DECLARED into the band the differential drops (`test/gemdos.py`, `machine`).

| Addr (ROM) | Name | Cases | Cost (insns / cycles) | Tier 3 (recreate / original) | Status | Verification |
|---|---|---|---|---|---|---|
| `0xfc4f6e` | GEMDOS trap #1 entry + the OS's own C door (`src/gemdos/trap1.S`) | 22 | 312 / 296 / 286 / 292 cycles per `Super` shape | **1.00** on all four `Super` rows | ✅ verified | 292 bytes byte-identical to the ROM with nothing spliced; the hand-built frame proved to be a real `trap #1`'s; the process frame read LIVE at the dispatcher (the epilogue rebuilds the `rte` frame over A1/A2 on the way out); all fifteen registers handed back; `Super`'s six arms incl. both D0 quirks; the framing path's only divergence measured to be the four bytes of `jsr` return address on the OS stack at `$16c6` |
| `0xfc94e4` | `gemdos_dispatch` (`src/gemdos/dispatch.c`) | 11 | 194 past the table | **0.65** past the table | ✅ verified | the counter's two stores from the ledger; the signed bound at three selectors and past it; the table's 88 six-byte records and its 38 stubs; and the termination record's twelve bytes identified — the one thing the C core is right not to have, because it is the 68000 frame of the `jsr` that armed it (see `## Not reconstructed, and why`) |
| `0xfc973e` | `gemdos_dispatch_selector`, the arms PAST that record (same file) | 32 | 604-640 per dispatched selector | **0.78-0.79** dispatched | ✅ verified | one battery with the row above (`test/test_gemdos_dispatch.py`, 43 cases): six selectors dispatched through our own leaves, bound by the table's address; every descriptor class's frame read off the ORACLE's stack (incl. `Mshrink`'s and `Pexec`'s, whose handlers do not exist); the descriptor REWRITE over five character-device selectors; the redirected arm reached as a slice for all five; and the HANDLE-RESOLUTION arm (`$fc9924`) whole: which argument word holds the handle (`$81` is `Fseek`, whose handle is the third), the two-level walk through `p_uft` and the table at `$8092`, and the EIHNDL a handle that names nothing answers with no call made. Two arms halt below it. Mutation 6/6 |
| `0xfc9348` | `Sversion` ($30, `src/gemdos/leaves.c`) | 1 | 5 / 96 | **0.50** | ✅ verified | the constant, and its D0 |
| `0xfc933e` | the undefined-selector stub (38 records, same file) | 1 | 5 / 88 | **0.42** | ✅ verified | EINVFN, and that it is NOT the bound check |
| `0xfc6c9a` | `Fgetdta` ($2f, same file) | 4 | 6 / 120 | **1.00** | ✅ verified | the whole longword over four DTAs incl. the snapshot's own |
| `0xfc6cac` | `Fsetdta` ($1a, same file) | 3 | 6 / 132 | **1.17** (accepted) | ✅ verified | the store from the write ledger, and the caller's own D0 back — the ROM writes no result |
| `0xfc6ce0` | `Dgetdrv` ($19, same file) | 7 | 8 / 124 | **1.00** | ✅ verified | the SIGNED byte at seven values incl. `$80` and `$ff` |
| `0xfc6cc0` | `Dsetdrv` ($0e, same file) | 6 | 39 / 762 | **0.98** | ✅ verified | the low byte stored with no bound check at four drives; the drive map answered against `_drvbits`; and the trampoline's parked return address pinned to a site the ROM really has a `jsr $fc4eac` at. A WHOLE-ROUTINE differential: on target our C takes the same `trap #13`, and off it the trap's register frame is declared into the band the diff drops |
| `0xfc9e1a` | `Tgetdate` ($2a, same file) | 6 | 6 / 104 | **0.97** | ✅ verified | the sign extension at both sides of bit 15 |
| `0xfc9ea2` | `Tgettime` ($2c, same file) | 6 | 6 / 104 | **0.75** | ✅ verified | the same, and why every afternoon answers negative |
| `0xfc9e2a` | `Tsetdate` ($2b, same file) | 9 | 22 / 308 | **0.60** | ✅ verified | VERIFIED ON ITS REJECTING ARMS: seven refused dates — a four-bit month, month 0, 31 April/September, and the leap pair (30 Feb 1988 vs 29 Feb 1987) — plus the YEAR bound shown to be DEAD CODE. The accepting arm halts at XBIOS `Settime` |
| `0xfc9eb2` | `Tsettime` ($2d, same file) | 6 | 18 / 228 | **0.76** | ✅ verified | the same shape: four refused times, plus the HOUR bound shown to be DEAD CODE. Same halt on the accepting arm |
| `0xfc8b70` | `Cconis` (GEMDOS $0b, `src/gemdos/console.c`) | 4 | 19-63 / 262-1014 | 0.89x, 0.90x, 0.91x | ✅ verified | the typeahead queue answering BEFORE the BIOS does — the arm's witness is not the answer ($ffffffff either way) but the trampoline's return slot, which a queued record leaves untouched; a handle whose device has no INPUT driver (PRN:) coming back as the BIOS dispatch's own scratch and not 0; and the ring both ways round |
| `0xfc8b8a` | `Cconos` (GEMDOS $10) | 3 | 48-57 / 840-946 | 0.96x, 0.97x | ✅ verified | `Bcostat` on p_uft[1] and nothing else, driven on the console and, with stdout moved, on the printer's BUSY line — the pair that says the leaf reads its OWN handle |
| `0xfc8bae` | `Cprnos` (GEMDOS $11) | 2 | 51-52 / 878-880 | 0.97x | ✅ verified | the MFP GPIP bit 0, swept both ways with every other bit inverted, and each read pinned in the ordered stream |
| `0xfc8bd2` | `Cauxis` (GEMDOS $12) | 1 | 63 / 1018 | 0.91x | ✅ verified | the AUX device's own queue and the RS232 input ring — and a record staged on the CONSOLE's queue leaving this answering no, which is what makes the index a claim |
| `0xfc8bee` | `Cauxos` (GEMDOS $13) | 2 | 57-58 / 946-948 | 0.97x | ✅ verified | the RS232 output ring's tail stepped and compared with its head, reading no hardware at all |
| `0xfc8e1c` | `Cconout` (GEMDOS $02) | 13 | 159-2859 / 2494-33858 | 0.86x, 0.87x, 0.90x, 0.91x, 0.92x, 0.94x, 0.96x, 0.97x, 0.98x, 0.99x | ✅ verified | the column counter's three arms (>= 32 SIGNED, CR to zero, BS back, LF untouched); TAB expansion at every column of one stop's width and its do-while at a stop; a glyph landing in the cell both layers' cursors name; and the poll it makes first |
| `0xfc8ed2` | `Cauxout` (GEMDOS $04) | 2 | 65-278 / 1068-3060 | 1.00x | ✅ verified | three instructions and a trap: the device's column counter untouched, and a key staged in the console's ring left where it was (no poll) |
| `0xfc8efa` | `Cprnout` (GEMDOS $05) | 1 | 253 / 3688 | 1.00x | ✅ verified | the same pair over the printer's whole YM2149 send |
| `0xfc8faa` | `Crawcin` (GEMDOS $07) | 1 | 81 / 1276 | 0.98x | ✅ verified | neither echo nor poll — no screen byte, no column, and one BIOS call |
| `0xfc8ff2` | `Cconin` (GEMDOS $01) | 3 | 412-443 / 4948-5584 | 0.92x, 0.93x | ✅ verified | the whole BIOS record back with only its LOW WORD echoed, the echo going to the INPUT device, a queued record read without the ring's head moving, and the queue rewinding when it empties |
| `0xfc900c` | `Cnecin` (GEMDOS $08) | 1 | 243 / 3640 | 0.97x | ✅ verified | no echo and the poll AFTERWARDS: two keys waiting, the first the answer and the second swept into the queue |
| `0xfc903e` | `Cauxin` (GEMDOS $03) | 1 | 69 / 1086 | 0.97x | ✅ verified | `Bconin(p_uft[2] + 3)` and nothing else. Driven with stdaux on the CONSOLE handle: on the captured machine it reaches `Bconin(AUX:)` ($fc2150), which `src/bios/bcon.c` defers |
| `0xfc9062` | `Crawio` (GEMDOS $06) | 5 | 72-284 / 898-3154 | 0.85x, 0.88x, 0.92x, 0.98x | ✅ verified | `cmp.w #255` on the WHOLE word ($40ff writes $ff), the read arm through the queue with no echo and no poll, and a plain 0 — not `$ffffffff` — when nothing is waiting |
| `0xfc90c2` | `Cconws` (GEMDOS $09) | 5 | 19-12486 / 276-207282 | 0.60x, 0.87x, 0.91x, 0.96x, 0.99x | ✅ verified | the SIGN-EXTENDED string byte, which leaves the column counter alone where `Cconout`'s word of the same value moves it; a TAB inside the string expanded by the same routine; a string crossing the last column into a wrap and a scroll; and the empty string, whose D0 is the caller's high half over the sign-extended standard handle |
| `0xfc91ea` | `Cconrs` (GEMDOS $0a) | 15 | 38-3986 / 538-48330 | 0.86x, 0.88x, 0.91x, 0.92x, 0.93x | ✅ verified | every key the ROM's own two nine-entry tables implement — BS and DEL one arm, LF and CR one arm, ^R, ^U, ^X — the ninth (zero) key sharing the DEFAULT arm, the erase MEASURING the line (a TAB taken back whole, a control code two columns), both buffer bounds (a maximum of 0 reads no key; a full line leaves the next key queued), and the length written back with nothing terminating the text |
| `0xfc7ed0` | `gemdos_pool_arena_alloc` (`src/gemdos/memory.c`) | 12 | 20 / 294 a request, 12 / 192 refused | **0.66**, **0.58** | ✅ verified | the bump cursor and both counters over four sizes; the refusal BEFORE the subtraction (nothing stored); `ble` proved by a request for exactly what is left; a zero request that still stores both counters (named settled); and both WORD-SIZED signednesses — a request with bit 15 set granted however little is left, and a cursor at/over `$4000` forming a NEGATIVE byte offset that wraps the address space |
| `0xfc7f1a` | `gemdos_pool_get` (same file) | 5 | 105 / 1504 from the arena, 84 / 1224 from the chain | **0.47**, **0.43** | ✅ verified | `class * 8` words for class 1 and class 16, the arena request one word MORE, the class word written below the record and the answer pointing past it; the chain POP with the record cleared over the link it was read from (attributed by staging the recycled descriptor holding its old fields); a spent arena answering 0 with no store; and the two arms proved independent — a chain record served with zero arena left |
| `0xfc7f9c` | `gemdos_pool_free` (same file) | 3 | 20 / 292 | **0.57** | ✅ verified | the record's first longword becoming the chain link over an empty and a non-empty chain; and the class read from BELOW the record — a class-16 record filed on `p_root[16]` and not `p_root[1]`, which a hard-coded class fails |
| `0xfc886a` | `gemdos_md_alloc` (same file) | 20 | 156 / 2280 a split, 40 / 636 an exact fit, 58 / 744 the largest | **0.53**, **0.94**, **1.00** | ✅ verified | NEXT-FIT: three free blocks all big enough, the rover moved over each, the successor always taken and the last one WRAPPING through the MPB — which a search from `mp_mfl` fails twice of three. The rover left at the predecessor (staged so it moves) and at `mp_mfl` on the MPB arm; the exact fit unlinked whole at no cost to the pool; the split's five stores in order with the block keeping `m_start`; the remainder from the class chain when one is waiting; a SPENT POOL refusing a split over free RAM while the same pool still serves an exact fit; `m_own` from `p_run` at a second value; the whole free list taken, emptying it and NULLING the rover; and `-1` measuring every block wherever the rover is, with the biggest staged in the MIDDLE and a SIGNED compare that never reports a wrapped length |
| `0xfc89dc` | `gemdos_md_free_insert` (same file) | 4 | 50 / 682 | **0.93** | ✅ verified | the sorted insert at the head, the middle and the end of the list with a used span either side so nothing merges; and the NULL-rover fix-up, which is what makes a pool `Malloc` emptied usable again. Its four coalescing arms are driven through `Mfree` below |
| `0xfc8aae` | `gemdos_malloc` ($48, same file) | 10 | 178 / 2576 an odd request, 78 / 1012 the largest | **0.55**, **0.86** | ✅ verified | `m_start` answered rather than the descriptor, and 0 for every failure; the 2-byte rounding at four sizes; the rounding turning a near miss into an EXACT fit (so no descriptor is cut) and pushing a request past a block it would have fitted; `-1` escaping the rounding — which is the whole reason it does not allocate; and a request for NO memory, which splits a block into nothing and the whole of it and still answers a real address |
| `0xfc8afc` | `gemdos_mfree` ($49, same file) | 15 | 86 / 1238 the snapshot's head, 114 / 1236 refused, 129 / 1816 both neighbours free | **0.78**, **0.84**, **0.70** | ✅ verified | head, middle and tail of the snapshot's own fourteen found by `m_start`; EIMBA over four wrong addresses incl. the FREE block's own start; the head unlinked through `mp_mal` read as a descriptor. ALL FOUR COALESCING ARMS: neither neighbour, successor only, predecessor only, and BOTH — three blocks into one with two descriptors recycled in the ROM's order — plus the rover walking successor → freed → predecessor, the only path the second fix-up fires on. The snapshot's own most recent allocation merges back into the free block with no staging at all |
| `0xfc895a` | `gemdos_mshrink` ($4a, same file) | 21 | 174 / 2484 a split, 21 / 314 refused (grow), 99 / 1176 refused (address) | **0.58**, **1.01**, **0.98** | ✅ verified | EIMBA over the same four addresses; EGSBF (−67) at +1/+2/+0x1000 with nothing stored; `bge` proved by shrinking to the block's own length (a ZERO-LENGTH descriptor); the SIGNED grow compare letting `$80000000` through; the rounding AFTER the check as the refused/accepted pair; the split's three stores with the block keeping its start, its owner and its place on the allocated list; shrinking to nothing; the remainder COALESCING with a block it touches and taking a recycled descriptor first; the zero-length remainder sorting BELOW a block at the same address; and **the ROM's unchecked `pool_get`** — a spent pool storing the remainder through NULL into the reset vectors, inserting an address-0 descriptor into the free list and reporting SUCCESS |
| `0xfc50ca` | `gemdos_fs_toupper` (`src/gemdos/fs_name.c`) | 15 | 16 / 212 | **0.53** | ✅ verified | both ends of `'a'..'z'` and past both; a wide argument read by its low byte alone; the result SIGN-EXTENDED from that byte, which is the half a reconstruction returning the plain character gets wrong. The compares' SIGNEDNESS is not observable — `$61..$7a` makes signed and unsigned the same function — and that is recorded rather than pinned |
| `0xfc539a` | `gemdos_fs_log2` (same file) | 11 | 54 / 462 | **0.90** | ✅ verified | powers of two, non-powers (the top set bit), and 0 answering -1 because the `subq.w #1` runs over a loop that made no pass. `asr.w` means a negative argument never returns; nothing pins that and the core says so |
| `0xfc55e6` | `gemdos_cluster_record` (`fs_disk.c`) | 9 | 7 / 160 | **0.92** | ✅ verified | a SIGNED 16x16 whose whole 32-bit product is the result, at both pseudo-cluster bases and at `$8000`, which an unsigned multiply wraps positive |
| `0xfc5c9a` | `gemdos_name_match` (`fs_name.c`) | 16 | 472 / 5190 | **0.38** | ✅ verified | the eleven positions with `?` and both sides folded; the DELETED arm's three outcomes, incl. the one place a `?` is REFUSED and the `$e5` pattern that finds a free slot; the attribute pair — a volume-label pattern is NOT an equality test, only a loss of the "entry attribute 0 matches anything" shortcut, so a pattern of 8 matches an entry of `$18`; and the asymmetric result, `clr.w` leaving the caller's high half where `moveq #1` clears it |
| `0xfc5d28` | `gemdos_build_fcb_name` (same file) | 21 | 213 / 2204 | **0.62** | ✅ verified | nineteen texts. A BARE `*` is not `*.*` — the stem's tail steps past it, so the extension pads with SPACE; the OVER-LONG skip is stopped by neither `*` nor space, which `"ABCDEFGHI*J.TXT"` is what distinguishes; a `*` whose next character is not a dot; a SPACE ending a field; and every one of the eleven bytes proved STORED over an `$a5` fill |
| `0xfc590a` | `gemdos_buffer_flush` (`fs_disk.c`) | 5 | 1102 / 12568 | **1.01** | ✅ verified | the early-out storing `-1` either way; the data and directory biases; and the FAT buffer written TWICE — its own record and `m_fsiz` below it — with the FAT's other sector proved untouched. The invalidate-before-write is the ROM's own order |
| `0xfc5a98` | `gemdos_buffer_get` (same file) | 15 | 1165 / 13470 | **1.01** | ✅ verified | hit / miss / evict over a staged six-buffer cache: the region chosen by arithmetic on the record at all three regions and the LIST that follows from it; MRU-to-front incl. the head writing its own link to itself; the LAST empty buffer preferred over the tail; a dirty victim written before the read; and the MEDIA-CHANGE protocol whole — `Mediach` truncated to a word, and a MAYBE flushing and re-reading THE HIT IN PLACE rather than evicting anything |
| `0xfc59f2` | `gemdos_rwabs_data` (same file) | 9 | 2119 / 23722 | **1.00** | ✅ verified | the overlap bound closed below and open above at all four record positions; the DATA list only, a FAT buffer left dirty beside it; another drive's buffer left alone; and a flush that is not an eviction — the buffer keeps the record, clean |
| `0xfc52de` | `Fforce` ($46, `src/gemdos/handles.c`) | 35 | 31 / 446 | **0.54** | ✅ verified | the SIGNED bound at both ends and at every one of the six slots; a source handle in 0..5 refused rather than aliased; and the pair that makes the descriptor's SIGN load-bearing — a record naming a DEVICE stores the device byte and takes no reference, one naming a FILE stores the handle NUMBER and counts the new holder (driven at two counts) |
| `0xfc52f8` | `gemdos_force_handle`, `Fforce`'s body over a named basepage (same file) | 36 | 23 / 316 | **0.74** | ✅ verified | every claim above runs through it, plus the one that is about the ARGUMENT: a handle forced into a staged CHILD's table with `p_run`'s left untouched — which is what `Pexec` needs it for |
| `0xfc5216` | `Fdup` ($45, same file) | 12 | 49 / 692 | **0.75** | ✅ verified | the search is for a free OWNER, at four positions incl. the last; ENHNDL (−35) over a full table with nothing stored; `ble`, so an unused slot takes the DEVICE arm and the new record names 0; and the ROM's own defect reproduced — the value copied, the count started at ONE however many holders the source had |
| `0xfc56c6` | `Fclose` ($3e, same file) | 24 | 42 / 648 device, 6173 / 72460 file | **0.63**, **0.98** | ✅ verified | every arm: the three device arms; EIHNDL; the FILE arm closes the OFD FIRST (`$fc57ee`, flags 0) whoever else holds it, then drops the count, and the last holder frees the OFD and releases the descriptor; EINTRN for an OFD already off its list; through p_uft; the dispatcher slice; and Fdup+Fclose+Fclose chained — TOS 1.02's DOUBLE FREE (the second close runs on the freed OFD, answers EINTRN and frees it again: a self-looped pool chain, the same record handed out twice) |
| `0xfc51de` | `gemdos_inherit_curdir` (`src/gemdos/process.c`) | 13 | 17 / 226 | **0.70** | ✅ verified | the byte into the child's `p_curdir[entry]` and the shared count bumped, at both ends of the sixteen slots and at a node the machine does not use |
| `0xfc5092` | `gemdos_resync_clock` (same file) | 9 | 272 / 3184 | **1.04** | ✅ verified | the probe's three ordered stores and the read-back masked `$0f0f` — read as two SEQUENCED statements, because `movep.w` reads +5 then +7 and two `io_read8`s in one C expression have no order; then thirteen BCD registers read TWICE into `$e94`/`$ea1` and compared, and six pairs of digits turned into the two DOS words at two readings that share no free digit. Every case declares a MEGA ST, and the plain-ST arm is an ORACLE claim (see "Not reconstructed") |
| `0xfc8092` | `gemdos_release_process` (same file) | 9 | 1015 / 12568 | **0.53** | ✅ verified | all four loops and the ORDER of the first two: a handle closed before the table is walked is not found again by it. The walk is BY OWNER (a descriptor the desktop owns survives); a directory entry of 0 is skipped and a NEGATIVE one decrements BELOW the table; the process's blocks coalesce back into the free list and the desktop's fourteen do not move |
| `0xfc817a` | `Pexec` ($4b, same file) | 8 | 10 / 144 | **1.75** (accepted) | ✅ verified | the only arm past which a differential cannot go: the mode bound, at both ends of the GAP that 1 and 2 are and at every word above 5 including both sides of the sign, with nothing stored. The record it saves to `$7560` is an ORACLE claim; the one it arms is the hole `$fc973e`'s row measures |
| `0xfc8242` | `gemdos_pexec_create`, `Pexec` past that record (same file) | 23 | 2808 / 41188 | **0.38** | ✅ verified | MODE 5 whole: the TPA as the WHOLE largest free block, the clear running eight bytes past the basepage (both ends of the overrun pinned), the environment measured to its double NUL and rounded at three lengths, an env pointer of 0 taking the parent's, the tail at four lengths incl. one past 125, device handles copied and a FILE `Fforce`d, all sixteen directories inherited zero or not, and both ENSMEM arms — the spent POOL, and a largest block below 256 with the environment given back. MODE 4: it touches no allocator at all, and builds the child's stack, `p_parent`, and A4/A5 from the segment bases |
| `0xfc8028` | `Pterm` ($4c, same file) | 11 | 1086 / 14054 to the epilogue | — | ⚠️ verified, unpriced | A CHECKPOINT at the `jsr $fc4fe8`, because it does not return: the exit code ZERO-extended at five values into the PARENT's `+$68`; `p_run` reassigned and the child released; the terminate vector called on BOTH shores (a staged routine and the captured machine's own bare `rts` at `$fc0670`), entered with the vector's own value at 4(sp), and `$408` read and NOT replaced; and the termination record left untouched — `Pterm` does not longjmp |
| `0xfc8086` | `Pterm0` ($00, same file) | 1 | 1090 / 14108 | — | ⚠️ verified, unpriced | `Pterm(0)` whatever the caller's argument word held |
| `0xfc7fd8` | `Ptermres` ($31, same file) | 4 | 1257 / 16174 | — | ⚠️ verified, unpriced | `Mshrink` on the process's own TPA first, and then the claim that separates it from `Pterm`: the kept block's descriptor goes to the RECORD POOL and the block onto NEITHER list, where `Pterm`'s goes onto the free one |
| `0xfc55fa` | `gemdos_copy_out` (`src/gemdos/fs_copy.c`) | 9 | 585 / 8710 | **0.35** | ✅ verified | one forward byte loop shared by three entry points; counts 0..0x180 and 0x8000 (an unsigned word); overlap upward SMEARS the first byte, downward shifts — not memmove |
| `0xfc5622` | `gemdos_copy_in` (same file) | 9 | 585 / 8710 | **0.35** | ✅ verified | the same loop with the ROM's (n, dst, src) order: handed the engine's same (n, cache, user) frame, it copies the other way |
| `0xfc564a` | `gemdos_bcopy` (same file) | 9 | 585 / 8710 | **0.35** | ✅ verified | byte-identical to $fc55fa; the copy GEMDOS calls by name |
| `0xfc4f10` | `os_swap_word` (same file) | 4 | 8 / 138 | **0.90** | ✅ verified | a word's bytes exchanged in place (`rotate_right16`); no caller reads the D0 it leaves; the FAT paths call it where the ROM does |
| `0xfc4f22` | `os_swap_long` (same file) | 4 | 10 / 172 | **0.92** | ✅ verified | all four bytes reversed in place, the ROM's own `ror.w`/`swap`/`ror.w` |
| `0xfc5672` | `gemdos_fcb_name_eq` (`src/gemdos/fs_records.c`) | 9 | 509 / 5944 | **0.72** | ✅ verified | eleven bytes folded through $fc50ca; `?` is a literal; the attribute byte is not read; a miss is `clr.w d0` over the caller's high half |
| `0xfc6b66` | `gemdos_fcb_to_text` (same file) | 11 | 97 / 984 | **1.05** | ✅ verified | `.`/`..` get no extension even a non-blank one; an extension starting with NUL still gets the dot; answers the address of the NUL |
| `0xfc6bd2` | `gemdos_dnd_path` (same file) | 4 | 209 / 2620 | **0.89** | ✅ verified | recursion root-first; each `\` overwrites the NUL so the text is UNTERMINATED (Dgetpath $fc6c84 backs up one); answers one past the last `\` |
| `0xfc6ebc` | `gemdos_fill_dta` (same file) | 2 | 245 / 3358 | **0.78** | ✅ verified | attribute; time, date and length swapped from the entry's LE; name via $fc6b66; the 21 search-state bytes untouched |
| `0xfc5c3c` | `gemdos_ofd_new` (same file) | 3 | 294 / 4334 | **0.41** | ✅ verified | arena / recycled / spent pool; length $7fffffff; OFD_DIR_DND is the DND's PARENT |
| `0xfc65a2` | `gemdos_dnd_new` (same file) | 5 | 425 / 6274 | **0.46** | ✅ verified | pushed first on the parent's child list; cluster swapped, time/date NOT; dirpos = parent OFD pos - 32 |
| `0xfc6fdc` | `gemdos_ofd_open` (same file) | 20 | 457 / 6748 | **0.45** | ✅ verified | first open takes the entry; a second open copies 12 bytes from +6 (two into OFD_DMD) and sets the first's OFD_NEXT_SAME_FILE; ENSMEM stores nothing |
| `0xfc6f5c` | `gemdos_handle_alloc` (same file) | 5 | 408 / 6060 | **0.60** | ✅ verified | free = OWNER 0, not value 0; ENHNDL at 75 owned; ENSMEM passes through with the record left claimed (count 1) |
| `0xfc70f6` | `gemdos_dir_zero_cluster` (same file) | 6 | 8561 / 107940 | **0.53** | ✅ verified | sectors 1..n-1 then 0 (answered, MRU) over two- AND four-sector clusters, dirty, through $fc5a98; geometry from the OFD's DMD, cache asked with the DND's — both pinned by a patterned cluster and the Rwabs traffic; ratio is whole-call incl. the staged Rwabs stub; the E_CHG arm unpinned |
| `0xfc7e24` | `gemdos_split_shift` (`src/gemdos/fs_io.c`) | 13 | 15 / 228 | **1.05** | ✅ verified | the remainder a WORD through the pointer, the quotient `asr.l`; the mask read out of the ROM's `$fd2fc8` table by a SIGNED word for any shift: -1 reads the word below it, 17 its second `$ffff`, 18 the ROM's next bytes; the shift modulo 64 (40 is the sign) |
| `0xfc61d6` | `gemdos_ofd_advance` (same file) | 4 | 19 / 338 | **0.82** | ✅ verified | position += n, the in-cluster offset only when asked, the length grown past the end SIGNED (`ble`: exactly to the end is not grown) with OFD_DIRTY ORed over the other flags |
| `0xfc7d2a` | `gemdos_ofd_seek` (same file) | 15 | 1528-1543 / 18608-18798 | **0.97**, **0.98** | ✅ verified | ERANGE both sides; 0's own arm; the walk from the start and from the CURRENT cluster (+1 when the old cursor sat at its cluster's end); a boundary left at the END of the cluster before it; backwards restarts; the offset stored BEFORE the walk, so an early chain end answers -1 with it moved; NO end-of-chain test on the last step; a drive with `m_clsizb` = 0 splitting through the word below the mask table |
| `0xfc6038` | `gemdos_fat_get` (same file) | 15 | 1459 / 17610 | **0.98**, **0.82** | ✅ verified | FAT12 through the FAT pseudo-file incl. a pair straddling two sectors; odd entries `asr.w #4` SIGNED — any odd entry with bit 11 set is negative; $fff → -1 only on an EVEN cluster (odd: word $ffff); FAT16; a negative cluster → cl+1 over the caller's D0 high half |
| `0xfc5f44` | `gemdos_fat_set` (same file) | 6 | 1788 / 22522 | **0.97** | ✅ verified | FAT12 read-modify-write with the neighbour's nibbles kept, the 12-bit mask; FAT16 word (the ROM swaps its value slot `10(a6)` in place — invisible, dropped stack band); the straddling pair; left DIRTY in the FAT cache, not written |
| `0xfc60f2` | `gemdos_next_cluster` (same file) | 12 | 1496 / 18166, 3646 / 49640 | **0.98**, **0.99** | ✅ verified | pseudo-cluster +1, FAT successor, first cluster from a fresh cursor; -1 with nothing stored; an odd $ff8 walking to cluster -8; allocation: the probe from the current cluster, lifted to 2, `% m_numcl` (the last two clusters never allocated), EOC then link, or first cluster + dirty for an empty file |
| `0xfc6218` | `gemdos_ofd_xfer` (same file) | 15 | 1521 / 18536, 12899 / 163628 | **0.89**, **0.74** | ✅ verified | head through the cache + copy routine; whole sectors via rwabs_data; clusters coalesced into one Rwabs per contiguous run incl. the second flush pass; leftover sectors; tail stepping at a cluster's start or end; a buffer of 0 answering a pointer into the cache; the chain ending early; the head-cluster count being the SECTOR INDEX ($fc6330: right for two-sector clusters and index 2 of four, wrong for 1 and 3 of four — pinned); an unknown copy address halts, unpinned |
| `0xfc5e9c` | `gemdos_ofd_read` (same file) | 5 | 1456 / 17574 | **0.93** | ✅ verified | clamped to length−position, signed; 0 at the end, for 0 and for a negative count, with no disk access |
| `0xfc5f1c` | `gemdos_ofd_write` (same file) | 5 | 7064 / 96264 | **0.92** | ✅ verified | no clamp: growing, allocating (one cluster, and two in one 4-sector Rwabs), a full disk moving 0, and a 0-byte write mid-sector that still DIRTIES the sector |
| `0xfc5e6a` | `Fread` ($3f, same file) | 4 | 3203 / 43584 | **0.57** | ✅ verified | a handle record and a standard handle via p_uft; EIHNDL; and the whole dispatcher slice against the ROM's own leaf |
| `0xfc5eea` | `Fwrite` ($40, same file) | 3 | 1624 / 20088 | **0.86** | ✅ verified | the same, dispatched on a standard handle |
| `0xfc7cce` | `Fseek` ($42, same file) | 8 | 1584 / 19392 | **0.97** | ✅ verified | modes 0/1/2 incl. ERANGE both sides; EINVFN for any other mode; EIHNDL BEFORE the mode is read; dispatched with its handle in the third word |
| `0xfc50fa` | `gemdos_dmd_alloc` (`src/gemdos/fs_drive.c`) | 6 | 1064 / 15286 | **0.38** | ✅ verified | the four records hung off each other; the pool spent at EACH of the four requests — the 0 stored into the parent before the test, the records got so far freed newest first, and the drive's table slot left naming the freed DMD; a SIGNED drive (-1 is the longword below the table) |
| `0xfc53c0` | `gemdos_dmd_build` (same file) | 11 | 1331 / 18804 | **0.51** | ✅ verified | eight geometries (the staged disk, 720K, FAT16 with every other BFLAGS bit, one sector per cluster, a 1000-byte sector, recsiz 0 reading the word BELOW `$fd2fc8`, a negative rdlen `muls`, a negative quotient `divs`) and ENSMEM; the BPB read in the ROM's ORDER — `fatrec` twice after the stores (a BPB under the DMD being cut); the staged `gemdos_fs.drive()` PROVED equal to what the ROM builds, which found the FAT pseudo-file's start at position 3 / byte 3 ($fc55be) the staging lacked. Unpinned: a zero `clsiz` (`divs.w` by 0, vector 5 — the host REFUSES); the root name `clr.b` over a pool-cleared record (equivalent) |
| `0xfc67de` | `gemdos_open_drive` (same file) | 15 | 1436 / 20260 log-in, 29 / 400 logged in | **0.54**, **0.95** | ✅ verified | log-in through the staged `Getbpb` (the first caller `hdv_bpb` has had) + the builder + the mask bit; `Getbpb` 0 → ERROR and ENSMEM with nothing kept; `asl.w` semantics (drive 15 = the sign bit, 16 = no bit, -16 = shift 48); every table index SIGNED incl. the curdir byte; a dead or absent curdir replaced by the first zero count from 1 (slot 0 skipped even when free), the old count NOT dropped; forty held → ERROR |
| `0xfc68dc` | `gemdos_path_start` (same file) | 12 | 75 / 964 | **0.98** | ✅ verified | `X:` (upper-cased, `'A'` subtracted as a word: `1:` is drive -16), a leading `\` → root, otherwise p_curdir's node; the current drive SIGNED; a new drive logged in underneath; a drive that will not open → 0 with the pointer NOT stored; the empty path reading past its NUL. Unpoisoned (the pointer is chased) |
| `0xfc7e52` | `gemdos_dot_name` (same file) | 13 | 34 / 376 | **0.66** | ✅ verified | "" = `moveq #1` (the whole register), "." -1 and ".." -2 only when the TERMINATOR follows, "..." / ".X" / "..X" ordinary, a terminator of '.' making ".." SELF, the terminator's low byte alone compared; the caller's high half on every other answer |
| `0xfc5e08` | `gemdos_split_path` (same file) | 12 | 364 / 3810 | **0.57** | ✅ verified | the tail NOT taken without the flag (tested BEFORE the dots, so ".." as a tail is 0), -1/-2 with nothing built, a zero-length component building nothing, and the three high halves of D0 — the caller's, 0 after a build, 0 after `$fc7e52`'s empty answer |
| `0xfc7e94` | `gemdos_strneq` (same file) | 10 | 74 / 850 | **0.47** | ✅ verified | STANDALONE (its caller is the dispatcher's device-name arm, a later band): no NUL stops it, a count of 0 is equal, case-sensitive, bit-7 bytes, and 0 over the caller's high half on a miss |
| `0xfc663c` | `gemdos_dir_search` (`src/gemdos/fs_dir.c`) | 40 | 3957 / 49972, 6194 / 84734, 4497 / 57726 | **0.75**, **0.82**, **0.81** | ✅ verified | first match (wildcards, attributes, only the low attribute byte); runs to the end and marks it OFD_SCANNED; an `$e5` search reuses a deleted entry or takes the end-of-directory entry unmarked; a directory ending with its chain; its OFD made on first use; DNDs made for every subdirectory passed beyond the SIGNED mark (from position 0 and, from the mark, raised SIGNED from −32); the known-name arm along the WHOLE child list; from the mark it answers the LAST DND MADE and un-reads the found entry; a spent pool at both requests |
| `0xfc696c` | `gemdos_find_dir` (same file) | 15 | 9084 / 111134, 1792 / 20484 | **0.75**, **0.72** | ✅ verified | two levels, take_tail on a directory and on a file, `.`/`..` climbing and reuse, staged DNDs with no disk read, the child list walked PAST its head (the common walk), `..` off the root, the tail left AT or PAST a missing component by miss kind, the end flag, the current directory, a drive that will not open. `tst.l a4` at $fc6a00 dropped (unreachable) |
| `0xfc6df4` | `Fsnext` ($4f, same file) | 5 | 2080 / 25596, 5985 / 74346, 5532 / 73344 | **0.88**, **0.84**, **0.83** | ✅ verified | the DTA's unaligned position/DND byte-wise; the next match with the DTA filled; across a cluster making the DNDs it passes; ENMFIL with the DTA untouched; a DTA position of −1 filling the DTA from a DND; the dispatcher slice |
| `0xfc57ee` | `gemdos_ofd_close` (`src/gemdos/fs_file.c`) | 11 | 6076 / 71088, 1591 / 19672 | **0.98**, **0.94** | ✅ verified | clean and dirty (cluster and length turned round in the OFD and back, time/date as stored, OFD_DIRTY never cleared); flag 2 writes length 0 and does not unlink, 6 does (`btst #2`); unlink at head, middle and tail; EINTRN before the flush; every buffer of every list flushed (dirty written and kept, clean EMPTIED) |
| `0xfc7824` | `gemdos_delete_entry` (same file) | 9 | 9178 / 116440, 34 / 564 | **0.97**, **1.02** | ✅ verified | a three-cluster chain, one odd cluster, cluster 0; the `$e5` mark and the flag-2 directory close flushing FAT and root; EACCDN for another process's open, after the caller's earlier handles were closed (and never released); an open file at another position ignored; the caller's second close of one OFD is unobservable (unpinned) |
| `0xfc772e` | `Fdatime` ($57, same file) | 7 | 1535 / 18760, 6023 / 70294 | **0.96**, **0.99** | ✅ verified | read (handle record and standard handle; D0 = the swapped date over the count), a NULL buffer answering the cache pointer's high half, write leaving the caller's buffer swapped, the slice; NO OFD check — the NULL-OFD arm halts here (oracle-only claims: GET swaps only the caller's buffer, SET never returns) |
| `0xfc7a68` | `Dfree` ($36, `src/gemdos/fs_leaves.c`) | 10 | 12401 / 175344 | **0.96** | ✅ verified | clusters 2..m_numcl−1 scanned, the two past the scan staged FREE and not counted; from cluster 2; the current drive; FAT16 incl. a used entry with a zero low byte; a new drive logged in; −1 for ENSMEM and a bad drive; the slice |
| `0xfc6c1a` | `Dgetpath` ($47, same file) | 6 | 291 / 3590 | **0.93** | ✅ verified | NUL over `$fc6bd2`'s last `\` (the root as ""), two levels, the current drive, EDRIVE with the empty string, the slice |
| `0xfc6d14` | `gemdos_sfirst` (`src/gemdos/fs_open.c`) | 2 | 3293 / 41986 | **0.82** | ✅ verified | the attribute WORD widened by $21 unless exactly 8; either miss EFILNF; the DTA filled from the path's 12-byte tail (caller bytes past a short name's NUL leak in), the widened attribute byte, the unaligned position and DND, then fill_dta; dta 0 searches and stores nothing (Pexec's use). The dead `tst.l` at $fc6d4a not kept |
| `0xfc6cf6` | `Fsfirst` ($4e, same file) | 18 | 12383 / 153320, 6479 / 88222 | **0.76**, **0.82** | ✅ verified | through p_run's DTA: widening (VOLUME alone not widened, a high-byte word widened, a read-only file found only because of it), hidden, lowercase and `?`, two levels down, a root child list three long, five misses with the DTA untouched; Fsfirst→Fsnext chained through `gemdos_fs.continued` (a real differential: both shores start from the carried state) to ENMFIL, in the root and in INNER; the dispatcher slice |
| `0xfc6a7e` | `Dsetpath` ($3b, same file) | 14 | 9082 / 111296, 6649 / 90030 | **0.75**, **0.82** | ✅ verified | the old node's count dropped FIRST and never restored on EPTHNF (sole and shared holders); the slot search after the drop (a sole holder's node comes straight back only when no lower slot is free); slot 0 skipped; `X:` picks the drive for the log-in but the walk runs on the CURRENT drive — and the walk's own log-in can take the slot just chosen (two drives share one node, count 2); a bit-7 letter is a negative drive whose log-in answer reads as an error; a signed p_curdir byte; forty held nodes EPTHNF before the walk; the slice. The 0-byte skip at $fc6adc is unreachable |
| `0xfc7606` | `gemdos_open` (same file) | 1 | 3697 / 46614 | **0.75** | ✅ verified | searched under $27 (never a plain subdirectory or the volume label); EFILNF for either miss (a missing DIRECTORY too); EACCDN for a read-only entry opened with any non-zero mode WORD, before a record is claimed; the mode word stored whole by handle_alloc |
| `0xfc75f2` | `Fopen` ($3d, same file) | 17 | 12589 / 155800, 3797 / 48010 | **0.75**, **0.80** | ✅ verified | modes 0/1/2 and high-byte mode words; two levels down; a list three long; a second open sharing the OFD found SECOND on a two-long files list; ENHNDL; ENSMEM with the record already claimed. UNPINNED: the dispatcher slice — the dispatcher's device-name arm ($fc9aca) halts |
| `0xfc7678` | `Fattrib` ($43, same file) | 19 | 8140 / 110144, 8129 / 97258 | **0.78**, **0.91** | ✅ verified | one byte 21 behind the search position moved through the directory's OFD into or out of the argument's own low byte (host slot ATTRIBUTE); get with no flush; set with the flag-2 close flushing everything; NOTHING checked (read-only cleared, any byte incl. the subdirectory bit, a directory reached through its ARCHIVE bit); EPTHNF vs EFILNF; answer = `ext.w` of the byte over a D0 high half 0 on every reachable arm (equivalent) |
| `0xfc77b2` | `Fdelete` ($41, same file) | 11 | 11651 / 148724, 3357 / 41576 | **0.92**, **0.78** | ✅ verified | $27 search; EFILNF for any miss; read-only EACCDN before anything is touched; delete_entry one entry behind the position: chains of 1 and 3 clusters freed and `$e5` on the disk, two levels down, a list three long, another process's open EACCDN, the caller's own open closed; the slice |
| `0xfc71b6` | `gemdos_create` (`src/gemdos/fs_create.c`) | 22 | 12573 / 171602, 14924 / 191688, 59282 / 802062 | **0.82**, **0.91**, **0.85** | ✅ verified | an existing entry DELETED through $fc7824 (not truncated) and its slot reused, the delete's answer IGNORED — a file another process holds gets a SECOND entry of the same name; only read-only or subdirectory refuse (`and.w #17`), a volume label replaced; a full root and a full disk EACCDN (the root cannot grow); a subdirectory grows by a zeroed cluster; a spent pool makes the root look full; the entry written in the cache, ENHNDL after it is on disk. ENSMEM via $fc6f5c unpinned (the ENHNDL arm) |
| `0xfc719a` | `Fcreate` ($3c, same file) | 4 | 12583 / 171736 | **0.82** | ✅ verified | the attribute byte `ext.w` then `and #$ef` (subdirectory bit masked), high-byte words. No slice: the device-name arm halts |
| `0xfc792a` | `Ddelete` ($3a, same file) | 16 | 17079 / 219182, 10378 / 127160, 5850 / 71178 | **0.85**, **0.94**, **0.79** | ✅ verified | non-empty EACCDN (the root refused only by its scan, which skips two entries); EINTRN for a child DND and for open files, BOTH reached by real call chains (the second needs duplicate DNDs: any position-0 search makes a fresh DND for each subdirectory it passes, because only the walk moves DND_SCANNED); NO current-directory check; the made OFD leaks; fields read from the freed OFD. Unpinned: an EMPTY root never returns (oracle-only claim; the C halts); a DND its parent does not list |
| `0xfc73ce` | `Dcreate` ($39, same file) | 10 | 33395 / 437942, 37866 / 483802, 32181 / 443180 | **0.78**, **0.78**, **0.95** | ✅ verified | `.`/`..` from the ROM templates $fd2fec/$fd3002 with the clock NOT swapped; `..` 0 for the root, the parent's cluster two levels down; the 50-byte OFD copy + close(6) unlinks every OFD opened earlier in the parent; ENSMEM paths leak the file and handle; a full disk rolled back through Ddelete |

THE THREE DISK ROWS' ~1.00 IS A RATIO OF THE WHOLE CALL AND NOT OF THE CORE, and it is worth reading
that way. `gemdos_buffer_flush`, `gemdos_buffer_get` and `gemdos_rwabs_data` each end in a `Rwabs`
through the STAGED 68000 driver, whose byte copy is 512 × 22 cycles — about 11k of each ~13k column,
identical on both shores. The core's own share is ~1-2k, so a change to it moves the printed ratio by
a fraction of what it moved the core by, and these three rows are a weaker instrument than their
figures suggest. NETTING THE STUB OUT (a per-row `staged_entry` measured from a zero-count `Rwabs`)
is a bench change and is PARKED below.

## Harness

| surface | state |
|---|---|
| Ghidra bootstrap of the ROM at `0xFC0000` | **DONE** 2026-09-13: `run.sh` + `reapply.sh` (≈4 min) → 1,292 functions, 1,219 decompiled, 137,555 of 196,608 B (70.0%) inside function bodies (the rest is the identified data: fonts, resources, the Line-F table); `names.txt` seeds 272 fn / 174 var / 44 cmt with zero apply failures; `a5` pinned to 0 over the BIOS/XBIOS (`unaff_A5` 308 → 107, none left in the pinned range); `COMPONENTS.md` maps every component but the aes/desk code boundary. Open: 73 functions fail to decompile (Alcyon's write-to-`(sp)` first-arg idiom, e.g. `Fread`, `Pexec`, `Setexc`) — listed in `COMPONENTS.md` |
| post-boot RAM snapshot (Tier 1 image) | **DONE** 2026-09-13: `make snapshot` → 1,048,576 B of a 1 MB ST's RAM, captured out of headless Hatari at the ROM's own VBL handler (`$fc06de`) on vertical blank 901, desktop up and idle; `tools/boot_snapshot.py --twice` measured the non-deterministic set over three boots — 1,929 B of AES/desktop idle scratch, recorded as its `MASK` — and `test/test_boot_snapshot.py` re-runs the ORACLE over noise-filled copies of every masked region, so no verified function may rest on a byte two boots disagree about |
| oracle ROM mode (`tools/recreate_kit`) | **DONE** 2026-09-13: the kit's ROM BINDING (`rom` / `rom_base` / `snapshot` / `stack_top` in `project.toml`) — the image is the 24-bit address space, the ROM read-only at `$fc0000`, no TOS trap model, and an I/O read no Phase-7 slot declares refuses the case by address. Pinned from C by `recreate_kit/test/test_rom_mode.py` (13 claims incl. the trap PAIR with and without the window) and from Python by `recreate_kit/test/test_rom_binding.py`; 825 kit tests green, and the six `.PRG` projects unchanged (zynaps 4,751 passed / 4 skipped) |
| Tier 3 numerator (`tools/recreate_kit/rom_bench.py`) | **DONE** 2026-09-14: the cores cross-compiled by `m68k-elf-gcc` with the SHIPPED ROM build's own flags (`atari/target.mk`, read by both makefiles), linked at `project.toml`'s `bench_base` = `$30000` and staged in the snapshot's free TPA, entered through `emu.run_bench` over the same case as the original — so every verified function carries a `recreate / original` ratio and not just a denominator. `make bench` prints the table; `test/test_tier3.py` gates it at <= 1.10 with an explicit `PERF_ACCEPTED` escape that goes stale loudly. Each row is a SECOND DIFFERENTIAL too (image, return value at the signature's width, callee-saved file, PSG/hardware ledgers, no unmodelled I/O read) — the surface for target-codegen defects, which Tier 1's host build cannot see (`docs/on-target-execution.md`, class 6). Measured sharp on three mutations: a core's `+1` → `+2` reds on the image, a target-only `psg.h` shadow selecting `reg + 1` reds on the return value, one reading `$ff8802` reds as an unmodelled I/O read. The entry overhead the ratio is net of (1 insn / 40 cycles, the 68000's reset) is measured on an empty function through BOTH oracle doors and required equal. **It couples the tree: the blob is ONE link over every `src/**/*.c`, so a core that does not compile for the 68000 now fails `make test` — which is the ROM's own constraint, arriving at the function rather than at the ROM build** |
| declared I/O map (`TRAP_MODEL.md` Phase 15) | **DONE** 2026-09-14: `io_seed={address: byte}` over any byte of the I/O page — the one door a case author uses (named Phase-7 slots are routed to their model, the YM2149 block refused by name); both cores serve and ledger it in order; an undeclared read still refuses by address; the six `.PRG` projects unchanged. First consumer: `Getrez` |
| rebuilt ROM boots in Hatari (`--tos`) | **DONE** 2026-09-13: `recreate/atari/` builds a 196,608-byte `TOS102RC.IMG` (header byte-identical to the original's, `checkrom.py` dereferences the MUPB; `.data`/`.bss` refused by the linker) whose boot stub paints 16 bands at the header-derived 60 Hz; Hatari runs it with `--patch-tos off` and a committed machine config |
| `TOSTEST.PRG` conformance ledger | **DONE** (seed) 2026-09-13: 14 call sites / 19 records + a screen CRC, ledger at $C0000, golden reproducible run-to-run; instrument identity (ROM/floppy/PRG sha256) pinned in every metrics file |
| `TOSBENCH.PRG` + boot-time surface | **DONE** (seed) 2026-09-13: boot surface = screenshot + 256 vectors + named sysvars ($000–$9FF pinned, clocks masked) at vblank 500 with a settle proof at 550 (boot metric 461 vbl / 1534 ticks); TOSBENCH times Bconout / Malloc / Fread on both clocks. **OPEN: Fread's own noise floor is 6.6 % (floppy rotational phase), wider than the 5 % bar — the floppy workload cannot be judged as designed; either sync to the index pulse, widen that row's bar to its measured floor, or move the read workload off the floppy** |
| write-through arm of the declared I/O map (`TRAP_MODEL.md` Phase 15) | **DONE** 2026-09-15: `io_seed={address: emu.write_through(byte)}` — a declared register whose later reads are served the byte the run's own store left, which is what lets a routine that re-reads what it wrote run to its `rts` instead of refusing; every store on the candidate goes through one `hw_write` so the two sides' ordered ledgers stay comparable. Pinned in the kit by `test/test_io_model.py`, `test/test_io_differential.py` and `test/io_model_probe.c` (the C side of the same claim), and in this project by `test/mfp.py`'s `WRITE_THROUGH_REGISTERS`. Its LIMIT is written down with it: the four pending/in-service registers are write-to-clear on the real 68901, and the claim holds only because every store these routines make is a pure `and` clear. Consumers: `Mfpint`, the MFP timer programmer, `Xbtimer`, `Rsconf`'s baud arm |
| schedule door on `run_bench` (Tier 3 for a routine that waits) | **DONE** 2026-09-15: `OS_SCHED_AT_READ` (`include/os.h`, `oracle/shim.c`) fires the scheduled store before the Nth READ OF THE WAIT ADDRESS rather than at a PC, because a PC belongs to one build and the cross-compiled column has nothing at the ROM's; the 7th `VERIFIED_CASES` field carries the schedule to both doors, and `rom_bench._vet_same_wait` compares the two runs' reads address by address so a build that spins differently cannot be priced as if it spun the same. Pinned by `test/test_sched_model.py`, `test/sched_model_probe.c` and `test/test_rom_bench.py` in the kit, and by `test/test_xbios_vsync.py` here. First consumer: `Vsync`, 0.97 / 0.92 |
| declared SEQUENCE (`TRAP_MODEL.md` Phase 16) | **DONE** 2026-09-16: `io_seed={address: [b0, b1]}` on any I/O byte — a Phase-7 NAMED SLOT included — so the Nth read of that address is served the Nth byte, which is what describes a register whose successive reads must DIFFER. ONE address-keyed table, consulted by both read paths before either model's own rule (`os_io_seq_install` / `os_io_seq_next` / `os_io_seq_store`, shared verbatim by `oracle/shim.c` and `src/hw.c`); the model that OWNS the address still keeps its ledger, its wide-read rule and its store rule, so a named slot's reads stay in `hw_events` and refuse at every width while any other byte's go to `io_events`. A read PAST THE END is a refusal on both shores, by ADDRESS and by READ INDEX (`osh_io_seq_spent` / `harness._vet_io_sequences_are_servable` on the oracle's side, the shared `os_refused()` plus the candidate's own `g_io_seq_spent{,_addr,_index}`, which is what makes `_seq_refusal_hint` name the read rather than offer the shape) — because a sticky last byte or a `0` would be a fabrication with the case's own declaration behind it. The candidate exports `g_io_seq_reset` / `g_io_seq_count` / `g_io_seq_spent{,_addr,_index}`, and `g_io_seq_spent` is the NEWEST name in `harness._HW_LEDGER_ABI`, so an `.so` predating the model fails the probe instead of serving a sequenced read out of the model below it. Pinned by `test/test_io_model.py`, `test/test_hw_model.py` and `test/test_io_differential.py`; a case that declares no list gets exactly today's rules. Consumers: `isr_acia`'s two-pass entry, `Bcostat` |
| shared record-and-refuse hook (`test/address_hook.py`) | **DONE** 2026-09-25: one `AddressHook` class per `.so` door (`recreate_call_vector`, `recreate_call_routine`, `recreate_call_gemdos_handler`, `recreate_call_disk_vector`), bound through `bind_pointer`: dispatch by key, a pass that opens and CLOSES around each candidate run, first-pass-only `calls`, the `CALLS_MAX` cap, and `staged()` — the one lifecycle, which refuses and REPORTS anything unstaged or outside a pass. Every guarantee pinned by `test/test_address_hook.py` (15/15 mutations killed). A new door is a new instance, never a copy |


## Wave log

* **Wave 1 (2026-09-13/14)** — three agents on disjoint paths, each reviewed by eight finder angles + a
  verifier, fixed, and committed by the orchestrator: (1) Ghidra bootstrap + `COMPONENTS.md` (the
  Line-F call mechanism, the a5 pin, 1,292 functions); (2) the kit's ROM mode + the boot snapshot +
  `Random`/`Giaccess`; (3) the rebuilt ROM image, boot surface, TOSTEST and TOSBENCH. Review found
  real defects in all three (a mask test that could not detect what it claimed, an unguarded stack
  band, I/O reads answered 0 silently, a stub at 50 Hz on an NTSC ROM, a benchmark that graded a
  failed workload "within the bar"). Parked from review: the kit-wide `OS_IMAGE_SIZE` limit
  (TRAP_MODEL.md), extracting a shared engine for LineAResolve/LineFResolve, deriving `gen_seeds.py`'s
  tables from the dispatcher signatures, and `projects/flyingshark/tools/extract_audio.py:155`
  catching only `(OSError, ImportError)` around its kit import (its siblings also catch `RuntimeError`).
  Parked from wave 2: `tools/test_hw_portability.py` has three PRE-EXISTING reds at HEAD (stale published
  figures for Wonder Boy's committed portability scan: at_risk 22/3658 vs the asserted 23/3888, 1 vs 2
  seeded-hardware writes) — fixing them means re-running that scan and re-publishing its numbers with the
  record that accounts for the move; the PSG-block pin that this wave moved to `os.h` is fixed (53 of 56).
* **Wave 2 (2026-09-14)** — three agents in parallel, each through the eight-angle review + verifier +
  fix cycle: (1) **Tier 3's numerator** — `tools/recreate_kit/rom_bench.py` + kit.mk's `$(BENCH_*)` rules +
  `bench/tier3.py` + `test/test_tier3.py`; rows are DERIVED from `test_boot_snapshot.VERIFIED_CASES`, so a
  verified function with no row is red (`tier3.UNPRICED`), STATUS's cells are pinned to `build/bench/tier3.txt`
  by `test_status.py`, and the second differential compares all four off-image streams and every refusal
  tally. (2) **the declared I/O map** (Phase 15) with `Getrez` as its first consumer. (3) **BIOS wave 1** —
  16 RAM-only BIOS/XBIOS leaves (the `## Verified — bios` section and 8 xbios rows above). Review found:
  host-only asserts that compiled away into fabricated returns on target (now `recreate_not_reconstructed`
  halts on both builds), a Supexec signature that was not the ROM's frame, a Cursconf return type that
  could not express two arms' `moveq #0`, Giaccess's missing interrupt-mask bracket (88 % of its measured
  speed-up — now `ipl.h`, 0.39 → 0.60), a kit make rule that silently disabled the numerator, and the
  stack-band guard from befc249 breaking Bubble Ghost (Alcyon writes its arguments back) and Wonder Boy
  (blits to the image's last word) — fixed by one formula: the band ends at the frame area and everything
  above it is COMPARED.
* **The Tier 3 finding, and the decision.** 17 of 30 measured rows are over the 1.10 bar and none is a
  reconstruction defect. At leaf scale one instruction is the whole ratio (Drvmap: 32 → 48 cycles = 1.50x),
  and three mechanisms account for every acceptance, each recorded in `bench/tier3.py`'s `PERF_ACCEPTED`
  with its measured cycles: **(A)** the C ABI's `uint8_t *image` load (`movea.l 4(sp),a0`, 12–16 cycles)
  where the ROM's dispatcher zeroes a5 once for every routine — a lever for the SHIPPED build (cores
  compiled with the image base a link-time 0), not for the C; **(B)** the Bcon* device dispatch as a
  compare chain under `-fno-jump-tables` vs the ROM's `jmp (a0)`; **(C)** Cursconf's arm selection vs
  `jmp TABLE(pc,d0.w)` — 2.29x, 104 → 238 cycles, the first lever worth a wave. Decision: the bar stays
  at 1.10 as the *ratio* instrument; acceptances carry their cycle deltas; the bar's shape for leaves (an
  absolute slack beside the ratio) is decided when the dispatcher wave exists to price a whole trap call.
* **Wave 3 (2026-09-15), BIOS wave 2** — four agents on disjoint sets, each through the finder/verifier/fix cycle:
  (S) the XBIOS screen + sound leaves (Physbase, Setscreen two of three arms, Setpalette, Setcolor, Vsync under Phase 8,
  Dosound, Setprt, Ongibit/Offgibit over Giaccess); (M) the MFP/timer/IKBD/serial XBIOS (Jdisint/Jenabint, Mfpint as a
  slice + the composed core candidate-only, the timer programmer's five clears, Rsconf, Ikbdws/Midiws, Kbdvbase, Initmous
  from the disassembly; Xbtimer's install arm with the RAW table byte); (I) the four interrupt handlers (HBL, VBL, timer C
  with the whole Dosound interpreter, ACIA) through a machine-entry case shape; (D) the trap #13/#14 dispatcher as
  `src/bios/trap.S`, proved by the numerator's TRANSCRIPTION differential (the whole register file required equal) and a
  byte pin against the ROM. Review found: Vsync sampling before the unmask (a one-frame-early return no tier can see);
  `void` cores clobbering a D0 the ROM preserves (Ongibit/Offgibit/Setscreen/Setpalette/Jdisint/Jenabint/Mfpint/Getmpb);
  Xbtimer entering Mfpint PAST its mask; a signed→unsigned branch swap in the transcription surviving every case (the byte
  pin); the ISR cores with no entry stubs (a C handler cannot sit on a vector); the staged caller in both bench columns
  (26 % leniency on the dispatcher rows, now `shared_entry`); the IKBD settle loop 14 % short of the ROM's elapsed time.
* **The leaf bar, decided.** A whole `Bios(10)` call is 496 cycles, 93.5 % of it the dispatcher; every mechanism-(A)
  leaf is 3–7 % of a real call. `bench/tier3.py` now applies the LEAF RULE: an (A)-only trap leaf is accepted when its
  excess is ≤ 40 cycles AND ≤ 7.5 % of (the measured full-dispatch cost, 464, read off the dispatcher rows + the leaf's
  own cost); nine leaves fall under it, `isr_vbl`'s +94 does not and keeps a written entry. The transcription rows are net
  of the staged caller on BOTH columns. Mechanism (I) — the ROM's entry glue in the original's column only — is retired
  by the ISR entry stubs (see the bios rows).
* **Kit items wave 3 named, and what became of them.** BUILT in wave 4 (below): the WRITE-THROUGH arm of the declared
  I/O map (a stored byte replaces the declared one for later reads — it unblocked Mfpint's enable half, the timer
  programmer, Xbtimer and Rsconf's baud arm), and the `schedule` door on `run_bench` with the 7th `VERIFIED_CASES`
  field (Vsync's Tier 3 row). BUILT in wave 5 (below): the declared ORDERED SEQUENCE per address (TRAP_MODEL Phase 16)
  — GPIP's second loop pass and Bcostat's declared bytes are its consumers; the ACIA data list per read and the FDC
  status are describable by it now and are deferred on their own evidence, not on the model. STILL NOT BUILT: the
  door's OTHER half, a registry of SLICES with a `stop_pc` for a routine whose arguments no `CALL` form can spell —
  which is why `$fc25b0` is verified and unpriced; a cross-stream order between image stores and hardware writes
  (Initmous mode 0). WAVE 6 BUILT NOTHING KIT-SIDE: the ACIA input chain and Bconout's six drivers were reconstructed
  entirely on the doors waves 4 and 5 opened (write-through, the read-triggered schedule, the declared SEQUENCE), and
  the one registry gap wave 6 opened was this project's own — `bench/tier3.py` could not price a routine reached
  through a RAM vector — and its review closed it with a third `_routine` relation (`VECTOR_ROUTINE_NAMES`), five rows
  and one deferral (see `## Not reconstructed, and why`).
  Parked from review: `test/trap.py`'s TRAP_BAND at SCRATCH+0x800 overlaps Supexec's staged decoys at +0x800/+0xa00
  (different cases, never staged together; `isr.py` asserts its own band clear of both) — move D's band. Set I's C cores keep
  the C ABI's `rts` entry as their own Tier 1 instrument beside the `.S` entry rows.
  Parked from the wave-4 review: `src/xbios/acia.c`'s two unbounded status spins are the same hole class as the timer
  programmer's was (a mis-addressed ACIA status hangs pytest rather than reds) and are left faithful for now; the
  trigger-door table (`TRIGGER_DOORS` + `triggers_not_runnable_at`) as a follow-up; `tier3`'s `RegArg` generalization, so
  `$fc25b0` can be priced at its own entry rather than only inside its callers; `VERIFIED_CASES` as a `NamedTuple` with
  defaults, now that the tuple is seven fields wide; the `os.h` I/O map as one struct rather than four parallel arrays;
  and a sharper refusal for an RMW helper (`hw_bset8`/`hw_bclr8`/`hw_and8`) aimed at a DECLARED address — today it reds on
  the Phase 10 value and the Phase 15 read stream, which is a correct red pointing one layer away from the cause.
  Parked from the wave-5 review: Zynaps's `ikbd_acia_isr` loop can now be modeled (lists on `$fffc02` and `$fffa01`) —
  deliberately NOT revisited, it is the control this model is measured against; `tools/hw_portability.py` knows nothing
  of sequences (a sequenced read is still classified by the model that OWNS the address); and `emu.io_seq_entries` has
  no memo, which is asymmetric with `io_seed_entries`.
* **Wave 4 (2026-09-15), the two kit doors wave 3 named** — two agents on disjoint doors:
  (A) **the WRITE-THROUGH arm of the declared I/O map** — `emu.write_through(byte)` is an `io_seed` VALUE rather than a
  second door, so a case declares which registers read back what was stored; every store the candidate makes goes
  through one `hw_write`, which is what makes the two sides' ledgers comparable at all. Its honest limit is written
  down: IPRA/IPRB/ISRA/ISRB are WRITE-TO-CLEAR on the real 68901, and the model's plain read-back claim holds only
  because every store these routines make is a pure `and` clear — found by the refusal naming `$fffa0b`, not by
  reading the datasheet first. The timer DATA register is a reload latch, which is why the programmer writes it and
  reads it once: the fifth clear STOPS the timer, pinned as a run-order assertion rather than as a comment. With it:
  `Mfpint` whole, the MFP timer programmer whole, `Xbtimer` (both arms) and `Rsconf`'s baud arm — the four rows above.
  The programmer's spin is faithful on target and CAPPED off target (`MFP_VERIFY_PASSES`, ending in `os_refused(0)`),
  because a mis-addressed register makes it never agree — which on target is the ROM's own hang and in pytest was a hung
  worker rather than a red. That closes the row's last mutation: 8/8.
  (B) **the SCHEDULE DOOR on `run_bench`** — a new `OS_SCHED_AT_READ` trigger keyed on the Nth read of the WAIT
  ADDRESS, because a PC belongs to one build and the cross-compiled column has nothing at the ROM's; the 7th
  `VERIFIED_CASES` field carries it, and `rom_bench._vet_same_wait` compares the two runs' reads per address so a
  build that spins differently cannot be priced as if it spun the same. `Vsync` is priced at 0.97 / 0.92 over two
  arrival counts, both PINNED UNDER the bar so that a vanished `ipl.h` bracket reds (measured 0.64 / 0.75 with it
  deleted). Phase 8's one aliasing hole is now measured in its Tier 3 form as well: a double-reading build agrees
  with the original at every EVEN spin count, so `PRICED_SPINS` holds an odd one.
  Review found: a stale candidate `.so` passing the ABI probe and segfaulting on the new `g_io_reset` (now
  `g_io_writeback_count` in the probe list + an `nm` pin); the timer programmer's faithful spin hanging pytest on a
  mis-addressed register (host-only pass cap ending in a refusal; the HUNG mutant now reds, 8/8); the bench came-due vet
  firing on a door stop and never on a resume (moved into `_bench_result`, pinned through the real door); a duplicated
  bench installer and never-came-due sentence; the per-byte store loop spelt on both shores (now one `os_io_store`);
  `baud_chip` indexing Python literals where its docstring claimed the image; a tautology where the odd-spin-count claim
  should be. Refuted: the RMW helpers latching a fabricated half on a write-through byte — two unconditional vets
  (Phase 10 value, Phase 15 read stream) already red it; a documented limit, a sharper refusal parked.
* **Wave 5 (2026-09-16), the DECLARED SEQUENCE and the two routines waiting on it** — one agent, the kit door and both
  consumers together. THE DESIGN DECISION was ONE address-keyed table rather than a list per Phase-7 slot beside a list
  per Phase-15 address: the second shape is one rule written twice, which is the wave-4 review's own "one rule, one
  helper" class (the per-byte store loop spelt on both shores), so `os_io_seq_install`/`os_io_seq_next`/`os_io_seq_store`
  are shared verbatim by `oracle/shim.c` and `src/hw.c` and are consulted from INSIDE each read path — the owning model
  keeps its ledger, its wide-read refusal and its store rule while the list only decides which byte is served. THE TWO
  CONSUMERS: `isr_acia`'s TWO-PASS entry (`io_seed={MFP_GPIP: [asserted, idle]}`, the shape the handler is a loop for),
  and `Bcostat`'s whole table, where the sequence is what lets one case sweep both sides of a bit in an ordered stream.
  THE FLOPPY VBL FINDING: `$fc1bc4` is NOT a poll loop, which `src/bios/vbl.c` used to say. It makes two WORD reads of
  `$ff8604` that a list describes exactly — but BETWEEN them it calls `$fc1e60`, which selects YM2149 register 14 and
  READS PORT A BACK to merge the drive-select bits. That is Phase 6's direct-PSG read-modify-write, a path this project
  has never used (its only PSG door is the `Giaccess` trap), and a run reaching both would be refused by the mixed-path
  guard — so the floppy service stays halted for a floppy wave, on the PSG's account rather than the FDC's.
  `Bconin`'s two remaining arms stay halted, and WAVE 6 FOUND THIS SENTENCE WRONG THREE TIMES — twice in the wave and
  once more in its own review. PRT: (`$fc2104`) reaches the parallel port through `Giaccess` (not a direct PSG access)
  and then spins on GPIP bit 0 until it is ASSERTED (not until it clears), so a declared GPIP list describes it exactly
  — it is a DEFERRAL, not a limit. And AUX: (`$fc2150`) does NOT wait on a ring an interrupt fills, which is what the
  wave-6 integration re-wrote this sentence to claim: it is `rs232_ring_get` on the INPUT ring, which a case stages,
  plus a flow-control tail of a PSG write and this wave's own transmitter prime. Both are deferrals; see
  `## Not reconstructed, and why`. `Bconstat`'s own halt is unreachable on the captured
  machine (its three drivers are all ring readers and all three are reconstructed — `src/bios/bcon.c`'s header says
  "four", which `test_bios_bconstat.py` contradicts: devices 1/2/3 carry drivers, 0 and 4-7 the bare `rts`); it stays
  because the table is RAM.
  Mutation sweep 24/24, with ONE first-pass survivor: an EMPTY list, which Python refused at the door and C admitted —
  the two shores disagreed about a declaration neither had a byte for. Closed with a probe case that pins the refusal on
  both. Review found: the staleness refusal's formatter crashing on a list (now renders it and prescribes the remedy a
  LIST really has — the case's shape, since a mark is refused at the door and a longer list answers a store no better —
  pinned by a store-then-read over a sequenced address); the ACIA handler's host bound spelt as an `assert` that would
  abort the pytest worker (now the kit's `hw_poll8`/`io_poll8` primitive, the read plus the model's own "could I still
  serve it?", so there is no cap constant anywhere and `kit_candidate.c`'s two poll cores dropped theirs too — the
  over-read-by-one mutant still reds, now naming the read and the address); a list on a named slot skipping the
  double-claim refusal in `seed_split`; the public `refusal_hints()` missing the sequence hint, and that hint being a
  guess — it is now a fact from the candidate's own `g_io_seq_spent{,_addr,_index}`, the newest names in
  `harness._HW_LEDGER_ABI`; the wide-read span resolver spelt on both shores (one `os_io_resolve_span`, with
  `os_io_seq_has_next` for the three `cursor >= length` spellings and `os_io_seedable` now derived from
  `os_io_seq_seedable`; breaking the named-slot exclusion on the oracle shore alone reds `test_io_model.py`);
  `io_seq_entries` re-spelling `io_seed_entries`' three address rules (one `_vet_io_address`); the bench door's
  split/merge/split (`_bench_io_seed` now drops the routed named constants and hands the caller's own dict back); and
  both probes' candidate helpers resetting one declaration and not the other (one helper each, plus a
  `cand_sequence_does_not_leak` row on both). Parked: one per-address byte-source table with a kind and a length
  (constant = a length-1 repeating sequence) collapsing Phase 15/16's two encoders; `run_bench` installing all three
  seeded models per run so `_bench_io_seed` becomes the identity; `test_status.py` deriving the Components table's
  ratio-range cells (the bios cell had drifted to 0.62–1.96x unnoticed).
* **Wave 6 (2026-09-19), BIOS wave 3** — two agents on disjoint halves of the character-device surface, each through the
  finder/verifier/fix cycle:
  (K) **the ACIA INPUT CHAIN** — the six routines under the IKBD handler's two KBDVECS slots: both 6850 service entries
  and their shared body, the byte splitter that sorts IKBD from MIDI by `cmpa.l #$c76,a0`, the ROM's own `midivec`, the
  scancode arm and the key-into-the-IOREC arm. Two case SHAPES for `isr_acia` now: the staged one that isolates the
  handler, and a REAL-VECTOR one that leaves the captured machine's own `$fc29fc`/`$fc2a0c` in KBDVECS and declares the
  two 6850s instead — the first case in this project needing TWO declared SEQUENCES at once (`$fffa01`'s line and
  `$fffc02`'s bytes), which is what assembles a three-byte relative-mouse report over three passes of the loop. THE
  FINDING: every routine TOS installs in a RAM vector is entered with A5 = 0, which the ROM's handlers establish once
  with `lea 0,a5` and which `src/bios/isr.S` had been spelling as the pushed image argument instead. It is pinned as an
  OPERAND of every vector call in `include/staged_call.h` — one `suba.l %a5,%a5`, 8 cycles a call — and it has NO Tier 1
  surface: delete it and every differential stays green, which is why the rows that carry it are PINNED rather than
  accepted (mechanism (K) in `bench/tier3.py`). It also un-halted timer C's auto-repeat injection at `$fc2c42`, which is
  a real call to `kbd_queue_key` now. Mutation 16/16.
  (C) **`Bconout` and its six drivers** — the table walk, the two 6850 senders, the printer's whole YM2149 send, the
  RS232 output ring, and the VT52 CONSOLE: the six-state machine at `$4a8`, the control codes `$07..$0d`, every escape
  the ROM's three jump tables really implement, and the four screen routines reached through RAM vectors. FINDINGS: the
  printer's serial redirect is a BYTE `btst` on a WORD field and so reads bit 12, not bit 4 — `$0010` prints and `$1000`
  redirects; the hold-off's `bcs` is UNSIGNED and the BUSY timeout's `blt` SIGNED, proved by a failure stamp ahead of
  the clock and by a clock half the longword range on; the escape SET is read out of the ROM's own tables rather than
  from a VT52 manual (nine table entries point at a bare `rts`); the cursor lock is a DEPTH whose unlock leaves that
  depth in D0, so `ESC l` puts the cursor in column `depth`; and the BLITTER screen set halts, the captured ST holding
  the CPU set. The console's POISON pass is OFF and stays off with its reason written down: the bytes the oracle writes
  ARE the driver's control state, so poison cannot be told from output — `vt52.canary` stands in for the pixel cases.
  `Cursconf`'s arms 0/1 stopped halting with it, and its `blink` row fell 2.29 -> 1.65. Mutation 21/21.
  STILL HALTING: `Bconin(PRT:)` and `Bconin(AUX:)`, the four blitter screen routines, `$fc4a42`, a console of six or
  more planes, and the floppy VBL — each with its reason in `## Not reconstructed, and why`.
  Review found: the console's cursor clamp transcribed as a SIGNED COMPARE where the ROM's `cmp.w / bpl` tests the N
  flag of the word difference — two different functions at the overflow window, and now driven there
  (`m68k_idioms.h`, `word_difference_is_negative`); the two `isr_acia, real vectors` rows pricing the ROM against the
  ROM — the cross-compiled handler jumps through KBDVECS too, so the six new cores were invisible to the gate as well
  as to those rows — closed with a third `_routine` relation, five priced rows and `acia_take_byte` deferred; the
  scroll and the clear running at 2x for a reason the compiler CONTRADICTED, respelled to the ROM's own loops (scroll
  2.03 -> 1.03, clear 2.24 -> 1.49) and the rows re-pinned; the IOREC ring step, the Dosound list plant and the
  differential runner each spelt three times by the wave's two halves (now `include/bios/iorec.h`, `include/sound.h` and
  `test/acia.py`); the A5 pin spelt five times in `staged_call.h`; and the `Bconin(AUX:)` and printer wait-site
  comments both describing something the code does not do.
  Parked: `-ffixed-a5` plus the ROM's own `suba.l a5,a5` in each `isr.S` stub as the deeper A5 lever (mechanism (K)) —
  zero per-call cost, one fewer allocatable address register everywhere, unmeasured; a kit `poison_keep=` span so a
  control-state routine can keep the automatic attribution pass (`vt52.canary` is the interim, hand-placed in five
  cases only); the poll primitives refusing the Nth re-read of a CONSTANT past `OS_SCHED_POLL_MAX`, because a spin on a
  constant that never satisfies its test hangs a worker today; `tools/addrs.py` binding ONE header (`addrs.h` is every
  wave's merge hotspot); a Tier 3 row for the console's SCROLL DOWN (`ESC I`/`ESC L` reach it, but only through Tier 1);
  timer C's auto-repeat injection has no registry entry and no Tier 3 row of its own; the console clear's two EDGE
  groups a scan line, which the ROM masks with `and.l`/`or.l` pairs where this fills a word at a time (the 1.49 row's
  remainder); and a process note — never run a mutation sweep in the background while editing, because a killed sweep
  skips its `finally` and leaves the mutation in the tree (it happened once this wave).
* **Wave 7 (2026-09-19/20), GEMDOS wave 1** — three agents on disjoint paths, each mutation-swept and
  merged by the orchestrator: (1) the `trap #1` ENTRY (`src/gemdos/trap1.S`, a byte-identical
  transcription), the dispatcher and the RAM-only leaves; (2) the CHARACTER-DEVICE group
  (`console.c`, fifteen leaves); (3) the MEMORY MANAGER (`memory.c`, the three trap leaves and the
  five routines under them). 36 verified rows and 98 new Tier 3 rows in one component.
  FINDINGS: the trap #1 entry frames into the calling process's own BASEPAGE rather than a shared
  save area, which is what lets `Pterm` unwind the PARENT; the dispatcher's descriptor word is a
  frame CLASS (4/8/12/14 bytes) plus bit 7 "this argument is a standard handle", with the
  rewrite/redirect split hanging off it; the YEAR bound of `Tsetdate` and the HOUR bound of
  `Tsettime` are DEAD CODE in TOS 1.02, both through a sign extension, and both are reproduced with
  a case; GEMDOS's clock is RAM advanced by an `etv_timer` hook (`$fc9cc0`), which is why
  `Tgettime`/`Tgetdate` are pure RAM reads; the console group's device model is `handle + 3`, with a
  typeahead queue between GEMDOS and `Bconin`, `Cconws` sign-extending bytes where `Cconout` does
  not, an empty `Cconws` returning the handle in D0's low word, and the `Cconrs` editor's real
  nine-key table whose ninth key is 0 and shares the DEFAULT arm; and the memory manager is NEXT-FIT
  with 2-byte rounding over a 16,000-byte record arena at `$2a6e` whose exhaustion is TOS 1.02's
  "out of memory descriptors", coalescing FORWARD then BACKWARD, EGSBF is −67 and not −37, ENSMEM is
  never used, and `Mshrink` on a spent pool writes a descriptor THROUGH NULL into the reset vectors
  and reports success. Mutation: G1 15/15, G2 20/20 (+2 coverage holes closed), G3 41/42 — the one
  survivor is the null guard on the forward merge, which no producible pool can reach.
  STILL HALTING: the dispatcher's three unreconstructed arms (redirected handles, handle resolution,
  the device-name arm of `Fopen`/`Fcreate`), the accepting arm of both clock setters, and the
  `Pterm` group — each with its reason in `## Not reconstructed, and why`.
  Process notes: agents' mutation sweeps against one `build/` serialise badly, and a killed sweep
  leaves a MUTANT BLOB behind — `build/bench/bench.*` must be deleted with the `.so`, not just the
  `.so` (it bit an agent this wave, and the orchestrator's gate now clears both before every run).
  Parked: `tools/addrs.py` binding MULTIPLE headers (this wave ran both conventions at once and the
  merge settled it one way — ROUTINE ADDRESSES and function numbers in `addrs.h`, where the
  registries key on them, and STRUCTURES in the group's own header — but the parser still reads one
  file, so a group with its own header still binds it by hand); a SHARED `AddressHook` class for
  `test/gemdos.py`, `test/isr.py` and `test/acia.py`, which are three copies of one
  dispatch-by-address recorder; a KIT-LEVEL DECLARED TRAP-FRAME EFFECT, so that the `savptr` poke is
  one convention rather than one wave's note; `bench/tier3.py` as ONE registry (address -> name,
  role, table) instead of three maps consulted in order; a STAGING BAND registry, so a battery's
  band is allocated rather than asserted against its neighbours; and a PER-MUTANT TIMEOUT in the
  sweep scripts (a mutation that unbounds a loop is detected by hanging, which costs a worker).
  Review found: the TARGET-SIDE BIOS DOOR — the cores took no `trap #13` on the bench blob, so the
  measured GEMDOS rows were our leaf against the ROM's leaf-plus-trap and twenty-three of them sat
  over the bar on an acceptance; the target build now takes the ROM's own trap and all 27 console
  rows re-measured under it, `Dsetdrv` with them (it was UNPRICED). The DISPATCHER'S POP COUNT lived
  in D2 across a `jsr` into drivers that write D2 (`xconout_rs232`, the bell) — now D3, which both
  ABIs preserve, with D2 clobbered. The SPLIT read a stale `m_length` across `gemdos_pool_get`
  (unreachable; the ROM re-reads it). `p_run` was defined in two headers and the memory manager's
  eight routine addresses in none of them. The hook was copied from `isr.py` without its call cap.
  Three copies of the basepage accessor and six of "read a longword out of an image".
* **Wave 8 (2026-09-22), GEMDOS wave 2** — two agents on disjoint groups, each mutation-swept and merged by
  the orchestrator. (F) THE FILE SYSTEM, over a verification shape this project did not have: a STAGED RAM
  DISK — a FAT12 image at `$68000` (44 KB) and three 68000 stubs in `hdv_rw`/`hdv_bpb`/`hdv_mediach`, so the
  ROM's own file system and the cross-compiled cores BOTH take a real `trap #13` into the staged driver
  (`recreate/README.md` has the section). Eight cores: the buffer cache (`_bufl[0]` FAT, `_bufl[1]` dir AND
  data, MRU to the front, LRU at the tail, the media-change answer TRUNCATED to a word and a MAYBE re-reading
  the hit IN PLACE), the flush that writes a FAT buffer TWICE because `fatrec` names the SECOND copy, the
  data-span transfer, and the 8.3 name layer — where a bare `*` is NOT `*.*`. (P) THE PROCESS GROUP and the
  handle machinery under it, twelve cores: `Pterm` does NOT longjmp (it `jsr`s into the trap entry's epilogue;
  the termination record is the FILE SYSTEM's critical-error target, and wave 7 had this wrong in three
  places), `Ptermres` = release then terminate, the 75×10-byte handle table at `$8092`, `Fdup` copying the
  VALUE but not the reference count (a ROM defect, reproduced), `Pexec` modes 0/3/4/5 with 1 and 2 a GAP and
  two dead branches, the basepage clear running eight bytes past its own end, `$8066` proved to be
  per-DIRECTORY-NODE reference counts (wave 7 named it `GEMDOS_PROCESS_FLAGS` — wrong), and the Mega ST
  battery clock re-read once per process end. The dispatcher's handle-resolution arm (`$fc9924`) came with
  it, which moved `$fc973e` from 0.82-0.83 to 0.78-0.79.
  REGISTRY: `VERIFIED_CASES` grew an EIGHTH field, `stop_pc` — a CHECKPOINT row for a routine that never
  returns — read through one `test_boot_snapshot.fields()` so the hundred rows with nothing to say about it
  did not have to be rewritten; `bench/tier3.py` gained a PER-TRAMPOLINE slice cost (the dispatcher's stub is
  three instructions, `Pexec`'s two — built and PRICED by one builder since the fix pass, so a stub whose shape
  changes cannot keep an entry cost nobody ran) and lists checkpoint cases under the table instead of reddening
  on them. The MAKEFILE's snapshot rule stopped depending on the whole of `include/addrs.h`: it depends on a
  CONTENT STAMP of the two constants `tools/boot_snapshot.py` really reads, plus the ROM image — every wave
  edits that header, and two agents' `make`s raced on the 15-second re-capture (the losing one failed at
  `$cc46`).
  Mutation: F 25/27 (two EQUIVALENT survivors, both written down), P 16/16. Independent reviews inside both
  agents found real defects (a 32-bit `Mediach` compare where the ROM truncates to a word; an assert in the
  wrong order).
  THE RAM DISK IS A FOURTH TENANT OF THE FREE WINDOW AND IS NOT DECLARED IN `project.toml`, on
  purpose and measured: the kit's `_vet_tenancy` knows three bands and has no named-tenant door, and
  growing `staging_bytes` to cover `$68000..$73000` reds `test_gemdos_fs_disk.py::test_the_ram_disk_
  span_is_clear_of_the_three_declared_tenants`, whose own arithmetic requires the case band to END
  at `$68000` (measured at the merge). It buys nothing either: Tier 3's blob can only reach the disk
  by first crossing the case band at `$60000`, which `_vet_bands` already refuses, and the span's
  emptiness in the snapshot is that battery's own claim. The door that would make it a declaration
  rather than an arithmetic is a NAMED TENANT LIST in `project.toml` — parked kit-side.
  Parked: the DMD BUILDER (`$fc53c0`) is the file system's next step (LANDED in wave 9, and the staged descriptor
  PROVED equal to what it builds; `hdv_bpb` now has its caller, `$fc67de`); the Mega ST clock wants a THIRD I/O column beside `OS_IO_DECLARED_CONSTANT`/`OS_IO_WRITE_THROUGH`
  ("a register a store does not reach"), without which the plain-ST arm stays an oracle claim; the shared
  `AddressHook` — the RECORD-AND-REFUSE hook is copied FOUR times (`test/isr.py`, `test/acia.py`,
  `test/gemdos.py` and this wave's `test/gemdos_fs.py`) and the fix pass could only level the copies, not
  merge them, so it is a **HARD PRECONDITION for the next file-system wave**: the fifth copy is not to be
  written (LANDED 2026-09-25, see below); NETTING THE STAGED DRIVER out of the three disk rows (`gemdos_buffer_flush`/`_get`/`gemdos_rwabs_data`
  measure ~11k of stub against ~1-2k of core, see the note under the table) — a per-row `staged_entry` from a
  zero-count `Rwabs`; and a BENCH TRANSCRIPTION CASE for `Pterm`'s epilogue path, which is the only surface that
  would see the exit code's D0 pin (see `## Not reconstructed, and why`).
  Still open in this component: the FILE LEAVES themselves (`Fopen`/`Fcreate`/`Fread`/`Fwrite`/`Fclose`'s file
  arm/`Fseek`, the `D*` group, `Fsfirst`/`Fsnext`) and the dispatcher's REDIRECTED (`$fd328a`) and DEVICE-NAME
  (`$fc9aca`) arms, which are the same functions seen from the dispatcher's side.
  Review found, and the fix pass landed, nine things. CORRECTNESS: `Pterm`'s `jsr` into the trap entry's epilogue
  left D0 UNPINNED, where the epilogue's first instruction re-stores it as the parent's saved D0 — a target-only
  corruption of every exit code, pinned now as an asm input and recorded unpinned by any surface; the battery
  clock's probe read its two registers in ONE C expression, where `movep.w` reads +5 then +7 and the ledger
  compares the stream in order; `Fclose` HALTED on the whole arm both `bge`s fall into, where the ROM answers
  EIHNDL for the half of it that names nothing — which is exactly what `Fdup` of an unused standard handle
  leaves, so a process owning one could not terminate; and the 8.3 name battery's staging band sat ON TOP of
  `test/gemdos_console.py`'s (`staging.SCRATCH + 0x600`, both of its hand-written neighbour assertions still
  passing). MEASUREMENT: `gemdos_resync_clock` was ACCEPTED at 1.18 on a rationale that blamed the ordered
  ledger, which was false on target — the excess was two image OFFSETS swapped each pass; respelt as pointers it
  measures 1.04 with the same reads in the same order and the acceptance is deleted. STRUCTURE: the
  record-and-refuse hook's FOURTH copy served calls from outside a pass, and four copies of `final_image`
  dropped the overflow guard the fifth had; `$87cc` was defined under two names and three wave-7 "process table"
  constants had no user at all (deleted, and `test/test_addrs.py` now refuses a second name for one address);
  and two arms had no candidate-side case — the dispatcher's resolved-FILE fall-through and `Pexec`'s copy of
  the outer termination record. Every one of the four correctness findings and both coverage holes was
  RED-before / GREEN-after under a mutation of its own.
* **Harness (2026-09-25), the shared `AddressHook`** — the file-system wave's HARD PRECONDITION, landed. The
  record-and-refuse hook is ONE class in `test/address_hook.py` (with `bind_pointer`, the one place a `.so` function
  pointer is bound): dispatch by key; a PASS WITH AN END — `recording()` opens one around each candidate run and closes
  it in `finally`, and any call while none is open is refused; `calls` = the FIRST pass alone (a pass counter, so the
  attribution pass is served but not recorded); the `CALLS_MAX` cap (moved from `test/case.py`); and ONE lifecycle,
  `staged(effects, describe_refusals)`, which drops the table on exit and FAILS the case if anything was refused — the
  battery supplies the wording, so the check cannot be skipped. Its four copies are thin uses: `test/isr.py` and
  `test/test_xbios_supexec.py` through `staged_routines` (one projection, one message), `test/gemdos.py` through
  `bound_handlers` (was `bind_handlers` + a separate `assert_every_handler_was_bound`), `test/gemdos_fs.py` through
  `staged_disk` (a fixed `{Getbpb, Mediach, Rwabs}` table, so an unmodelled BIOS function is REFUSED where it was
  served as `Rwabs`). The wave-8 note had one copy wrong: `test/acia.py` never had one; Supexec's was the fourth and
  the weakest. `final_image` was already one helper. Review of the first merge (5 finders) found the pass was never
  CLOSED — a stray call after a case was appended to that case's `calls` and, in the two GEMDOS modules, SERVED out
  of its table; fixed, RED-before/GREEN-after. Mutation 15/15, and the pass-close, the exit refusal and the table
  drop are caught ONLY by the new `test/test_address_hook.py`, which drives the real Supexec door. Suites 2,485 /
  1 skipped, guarded the same (3,292 runs), Tier 3 table byte-identical.
* **Wave 9 (2026-09-25), GEMDOS fs wave 3 band 1 — the DRIVE, the I/O ENGINE and the RECORD LAYER.** 33 routines, three
  agents on disjoint files after a read-only call-graph map found the file system's one STRONGLY-CONNECTED COMPONENT:
  the FAT is read as a pseudo-FILE through the same transfer engine it serves ({`$fc7d2a` seek, `$fc6038`/`$fc5f44`
  FAT get/set, `$fc60f2` next_cluster, `$fc6218` xfer, `$fc5e9c`/`$fc5f1c` read/write}), terminating only because
  the FAT OFD's clusters are negative — so it was built as ONE unit. The record layouts (OFD/DND/DTA/directory
  entry, every field cited to a ROM instruction) landed in `include/gemdos/fs.h` FIRST so three agents shared one
  spelling; the map's guesses it refuted: OFD+0x14 is the HOLDING directory's DND, OFD+0x2c is not a chain, the open
  mode is never read, DND/OFD time and date are NOT byte-swapped. (A) `src/gemdos/fs_drive.c`: the DMD builder
  `$fc53c0` — the staged descriptor is now PROVED equal to what the ROM builds, which found the FAT pseudo-file's
  start at position 3 the staging lacked — and `open_drive` taking the ROM's own `trap #13` Getbpb on target, the
  path start, dot names, the component splitter. (B) `src/gemdos/fs_io.c`: the SCC plus `Fread`/`Fwrite`/`Fseek`;
  the dispatcher's file arm is now a full slice differential against the ROM's own leaves; the ROM's `-2(a6)` frame
  word has a host stand-in in the dropped stack band with a re-entrancy assert. (C) `src/gemdos/fs_records.c` +
  `fs_copy.c`: the three byte copies (one loop), the byte swaps, the DND/OFD makers over the pool in its three
  states, handle allocation, directory-cluster zeroing, name/path/DTA text. FINDINGS: odd FAT12 entries come back
  NEGATIVE for any value with bit 11 set (`asr.w #4`); `$fc6330` finishes the head cluster with the sector INDEX, so
  four-sector clusters transfer wrong at head indices 1 and 3; the allocator never uses the last two clusters; seek
  has no end-of-chain test on its last step; a zero-byte `Fwrite` dirties a sector; `$fc50fa` leaves `$8380[drv]`
  naming a freed DMD on failure; `$fc67de` never drops the old curdir's count; the second open's 12-byte copy runs
  two bytes into OFD_DMD. REVIEW (6 finders: C faithful to the asm everywhere) found the real defects at the SEAMS:
  `$fc7e24` COMPUTED its mask where the ROM indexes `$fd2fc8` by a SIGNED word — and A's builder yields log2 -1 for a
  zero sector size (RED-before/GREEN-after, now one `gemdos_bit_mask()` both files use, shifts modulo 64 through
  `asl_word_by`/`asr_long_by`); the builder read `fatrec` at entry where the ROM reads it after its stores (RED/GREEN);
  a runtime `fn` into an `"i"` asm constraint (now a macro); a zero `clsiz` dividing on the host (now a refusal);
  two surviving `dir_zero_cluster` mutants and its unpinned loop order (killed/pinned); and the duplication three
  concurrent agents make — a staged-disk run wrapper ×6 (now `gemdos_fs.run`), a second staging registry (now
  `staging.Registry`, and every fs tenant claims through `gemdos_fs.SPAN` — which found a transfer buffer overlapping
  the record slots), constants spelt in C and Python apart (now one parse of the fs headers), `D0_CALLERS_HIGH_HALF`
  ×3 (now the kit's `set_low_word`). Mutation: the bands 51/51, 58/58, 64/65; after the fix pass 182/184 over all
  three, the two survivors EQUIVALENT (the root name `clr.b` over a pool-cleared record; the split mask's `ext.l`,
  of which only the low word is stored). Unpinned: the disk-error/media-change longjmp arms; a FAT access at the
  FAT's last byte (a stale stack byte); an unknown copy address in `$fc6218`; the zero-`clsiz` divide; the `"i"`
  constraint (no build flag isolates it). Parked: a kit-level `poison_exempt` for machine-owned pointers (savptr,
  pool heads — five fs batteries run unpoisoned for that reason); the RAM disk and user buffer as `project.toml`
  tenants; `claim()` allocating addresses; running the pure-arithmetic routines without the whole staged disk.
* **Wave 9 band 2 (2026-09-25) — the DIRECTORY LAYER and the FILE LAYER.** Two agents: (D) `src/gemdos/fs_dir.c` — the search
  `$fc663c`, the walk `$fc696c` and `Fsnext`, over a staged directory tree; (E) `src/gemdos/fs_file.c` — close `$fc57ee`, delete
  `$fc7824`, `Fdatime`, and `Fclose`'s FILE arm in `handles.c`; `Dfree`/`Dgetpath` in a new `fs_leaves.c` (moved there by the fix
  pass so the drive layer stays at the bottom). FINDINGS: the DND tree is built as a SIDE EFFECT of searching, and a search from
  the mark answers the LAST DND MADE rather than the matched entry's; the walk's tail lands AT or PAST a missing component by how it
  missed; `$fd2fe8` is the mask table's two `$ffff` entries read as -1; a close flushes EVERY buffer of every drive, writing dirty
  ones and EMPTYING clean ones; OFD_DIRTY is never cleared; `Fdatime` has no OFD check; `Dfree` never counts the last two clusters;
  and a real TOS 1.02 DOUBLE FREE — `Fdup` gives the new descriptor its own count of one over the same OFD, so closing both frees
  the OFD twice: a self-looped pool chain and the same record handed out by the next two `pool_get`s, pinned by chained
  differentials. REVIEW (4 finders; C faithful to the asm) found the tests weaker than their claims: find_dir's sibling walk (the
  COMMON walk) and the known-name walk never crossed a link, the mark-raise signedness was unpinned, a Dfree case could not see
  what it named — each proved SURVIVED then killed by staged data — and band 2 had re-invented band 1's host frame word four times
  over three mechanisms: now ONE host-slot table in `include/gemdos/gemdos.h` (`GEMDOS_HOST_SLOT_*`, claim/release with a held mask,
  so nesting is ASSERTED) and one table-driven placement test; one leaf/dispatch-slice door with one table test over every fs leaf;
  `tools/addrs.py` reads `(-1)`. Mutation 114/116 (fs_dir 47/47, fs_file 41/42, handles 7/7, fs_leaves 14/14, shared 5/6): the
  survivors are the caller's unobservable second close in `delete_entry` and the held-mask assert (an equivalent guard, proven live).
  Unpinned: the NULL-OFD `Fdatime`; `$ff8`..`$ffe` chain ends in delete; `ofd_close`'s failing seek; `Fclose` on p_uft 1..5; a
  parent with children but no OFD; `Fsnext` on a garbage DND; Fsnext's re-read of p_dta after the search ($fc6e7e/$fc6ea0,
  equivalent on reachable data); Dfree/Dgetpath storing the resolved drive into their argument word (dropped band).
* **Wave 9 band 3 (2026-09-25) — the NAME and CREATE leaves.** `src/gemdos/fs_open.c` (sfirst, Fsfirst, Dsetpath, open, Fopen,
  Fattrib, Fdelete) and `src/gemdos/fs_create.c` (create, Fcreate, Ddelete, Dcreate) — 11 routines, two agents. FINDINGS: `create`
  DELETES an existing entry rather than truncating it and ignores the delete's answer, so a file another process holds gets a
  SECOND entry of the same name; `Dcreate`'s 50-byte OFD copy + close(6) unlinks every OFD opened earlier in the parent; `Ddelete`
  has no current-directory check and an EMPTY root makes its child walk run from address 28 forever; any position-0 search makes a
  fresh DND for every subdirectory it passes (only the walk moves DND_SCANNED), so a directory can carry duplicate DNDs;
  `Dsetpath("B:\X")` logs B: in but walks `\X` on the CURRENT drive, and the walk's own log-in can take the node slot Dsetpath just
  chose; `Fopen`/`Fdelete` answer EFILNF for a missing DIRECTORY; the $27 search attribute means Fopen/Fattrib/Fdelete never name a
  plain subdirectory or the volume label, yet `Fattrib` checks nothing and can clear a directory's subdirectory bit reached through
  its archive bit. REVIEW (3 finders; C faithful) found the Fopen mode tested as a byte by nothing (it is a WORD), a FABRICATED
  staging for Ddelete's EINTRN arms — now both reached by REAL call chains — and twins of committed helpers: the fix pass exported
  the drive prefix and node slots (fs_drive.h), descriptor_of/release_descriptor (process.h), next_entry, the walk flags and
  search attributes (fs_dir.h), ENTRY_BEHIND_POSITION and the open modes (fs.h), and gave the tests ONE `gemdos_fs.continued`
  (chaining one run's end state into the next — a real differential) and ONE `gemdos_fs.routine` door for unnumbered routines.
  Mutation 142/153, the 11 survivors argued equivalent or unreachable (listed in the rows). `path_start` 0.99 → 0.98 (the shared
  prefix parse inlined). Unpinned: the DISPATCHED Fopen/Fcreate — the dispatcher's device-name arm $fc9aca halts — which is the
  next step.
* **Next** — THE REST OF GEMDOS: `Frename` (`$fc7af0`, which calls the Fopen/Fcreate/Fclose entry points); the dispatcher's
  device-name (`$fc9aca`, which unblocks the dispatched Fopen/Fcreate) and redirected (`$fd328a`) arms; the Pexec loader `$fc85ea`.
  Then VDI and Line-A.
  Earlier lists, still open: the aes/desk code boundary; the 73 Alcyon write-to-(sp) decompile failures.

## Suite

`make test` — **3,113 passed** (1 skipped) and `make guarded` the same count (3,946 candidate runs guarded, no fault),
re-summed at the fs wave-3 band-3 commit on 2026-09-25 after a forced relink of the oracle and every candidate;
`make bench` judges 303 rows (224 ok / 58 accepted / 12 pinned / 9 rule, none OVER or DRIFTED), re-counted from the
printed table. The kit's own suite: **1,126 passed**. Zynaps unchanged (4,751 / 4 skipped) and Flying Shark unchanged
(3,851) as the PRG controls. `names.txt`: 464 fn / 307 var / 224 cmt.

Environment note: the Xcode-licence gate that wave 3 worked around (`/Library/Developer/CommandLineTools/usr/bin` +
`SDKROOT`) was cleared with `sudo xcodebuild -license accept` before wave 4; the system `cc`/`make`/`git` are in use again.

## Not reconstructed, and why

**bios — `acia_take_byte` (`$fc2a42`) is verified but UNPRICED, and it is the only one left.** Wave 6's review found the
other five priced by nothing at all: `bench/tier3.py` resolved a case's entry through the trap dispatch table or
`isr.HANDLER_OF_TRAMPOLINE` and these are neither — they are reached through KBDVECS, by the handler — while the two
`isr_acia, real vectors` rows that were said to cover them run the ROM's chain on BOTH columns (the cross-compiled
`isr_acia` jumps through KBDVECS exactly as the ROM's does, so our C never executed under them). A third relation,
`VECTOR_ROUTINE_NAMES`, now gives each of the five a row of its own: 1.40, 1.75, 1.53, 1.61 and 1.85, mechanism (A) plus
(M), the register-argument marshalling the ROM gets free from A0/D0. `acia_take_byte` is DEFERRED behind a case that
enters it directly — every case reaches it through one of the two service entries, so nothing pins the register contract
a row would have to be called through.

**bios — the console's four BLITTER screen routines** (`$fc47be`, `$fc4852`, `$fc48b6`, `$fc4936`): TOS 1.02 installs
them on a machine with a blitter; the captured ST holds the CPU set, and each reconstruction halts on a vector that is
not it. Likewise a console of six or more bit planes — the ROM's own fill table at `$fd15ba` has three entries — and
`$fc4a42`, the console re-initialisation after a resolution change (still `Setscreen`'s halt).

**bios — `Bconin`'s two remaining drivers are both DEFERRALS, not limits**, and the second half of that is wave 6's own
correction. `Bconin(PRT:)` (`$fc2104`): every chip access is `Giaccess` and its wait is a declared GPIP list away (it
waits for BUSY to be ASSERTED). `Bconin(AUX:)` (`$fc2150`) was recorded as needing an interrupt to fill the RS232 input
ring; it does not. Its body is `lea $c54,a0 / bsr $fc2892` — the same blocking ring reader `rs232_ring_get` already is,
on the input ring instead of the output one, which a case STAGES exactly as `test_bios_bconin.py` stages the console's —
and then a flow-control tail: the mode byte at `32(a0)`, a low-water compare against `10(a0)`, and either a direct
`$ff8800` read-modify-write dropping RTS (`psg_seed` serves it) or an XON planted at `33(a0)` and the MFP TSR test and
transmitter prime THIS WAVE RECONSTRUCTED for `Bconout(AUX:)` (a declared `$fffa2d` serves that). What is missing is the
cases and one parameter — `rs232_ring_get` names `IOREC_RS232_OUT` where the ROM takes its ring in A0.

**bios — honest gaps in the console.** WHICH `b??` `cell_address`'s two clamps are is now HALF DRIVEN. Wave 6's review
found them transcribed as signed compares where the ROM's `cmp.w / bpl` tests the N FLAG OF THE WORD DIFFERENCE — two
different functions once that subtraction overflows — and `test_bios_vt52.py` drives the difference at the overflow
window (a column of `$8000` and `$8027` clamp; `$8028` does not), so `bpl` against `blt` is pinned and
`advance_cursor`'s own `blt` is pinned by being the other answer. What is still read off the disassembly and not driven
is `bpl` against a `bcc`: it would take a coordinate whose unclamped cell address is not in the machine's megabyte, so
the reconstruction's own bound fires where the original walks its address space. And
the console's poison/attribution pass is OFF: the bytes the oracle writes ARE the driver's control state, so poison
would be indistinguishable from the routine's own output; `vt52.canary` stands in for the pixel cases.

**bios — the floppy VBL** (`$fc1bc4`, reached from `isr_vbl` past the `flock` gate) stays halted on the PSG's account:
it merges drive-select bits with a direct YM2149 read-modify-write, a path this project has no door for (see wave 5).

**gemdos — the dispatcher's remaining unreconstructed arms are whole COMPONENTS, not branches.** The REDIRECTED arms
(`$fd328a`, 19 entries, reached when `Fforce` has pointed a standard handle at a file) are `Fread`/`Fwrite`/`Fseek`;
and `Fopen`/`Fcreate`'s device-name arm (`$fc9aca`) needs both handlers. The third, the HANDLE-RESOLUTION arm
(`$fc9924`) over the open-file descriptors at `$8092`, is RECONSTRUCTED as of GEMDOS wave 2 — what still halts below it
is the CHARACTER-DEVICE routing a negative resolution takes (`$fc99bc`). Each halts on both builds. The
PROCESS-TERMINATION RECORD at `$7ef4` is omitted
rather than halted, because the ROM arms it before any reconstructed arm and a halt would stop every case: it is the
68000 frame of the `jsr` that armed it, which a C core has no counterpart for, and `test_gemdos_dispatch.py` measures
the hole at exactly twelve bytes. ON TARGET THE OMISSION HAS A CONSEQUENCE, and it is worth writing down before
anything depends on it: a ROM built from these cores would leave `$7ef4` holding whatever last wrote it, so the FILE
SYSTEM's critical-error abort (`$fc5986` and four more, through the `longjmp` at `$fc4f54`) would jump through a stale
record — and so would `Pexec`, which saves the outer record and arms its own. It is NOT `Pterm`: wave 7 said so and
wave 2 of this component disproved it — `Pterm` `jsr`s into the trap entry's epilogue at `$fc4fe8` and touches the
record not at all (`$fc8028`'s row). Nothing compiles these cores into a ROM yet — the bench blob enters the
dispatcher as a C function and never terminates a process — so nothing is broken by it today, and nothing pins it
either. The surface that would is a Tier 2 row over a call that aborts.

**gemdos — `Tsetdate`/`Tsettime` are verified on their REJECTING arms only.** Both end in XBIOS `Settime`
(`$fc50b4`, a `trap #14` that writes the 6301's clock over the IKBD ACIA), which is not reconstructed. Every bound the
two routines apply is in reach — and two of them turn out to apply to nothing at all: the year bound and the hour bound
are DEAD CODE in TOS 1.02, both through a sign extension, and both are reproduced with a case.

**gemdos — the PROCESS group's three halts and one modelling limit.** `Fclose` of a handle that names an OPEN FILE
— which is `$fc57ee`, the file system's own close, and NOT the whole of the arm both `bge`s fall into: `$fc51c0`
(the two-level handle -> record lookup) is reconstructed, and a value of 0 there is a handle that names nothing and
answers `EIHNDL` with no store, which is what `Fdup` of an unused standard handle leaves and what a process owning
one meets on its way out. Only a POSITIVE value halts. Then the dispatcher's CHARACTER-DEVICE ROUTING under the
handle resolution (`$fc99bc`, which needs `Fread`/`Fwrite` over `console.c`'s leaves); and `Pexec` modes 0 and 3,
which LOAD (`$fc6d14` looks the file up, `$fc85ea` relocates it). The limit is the Mega ST battery
clock: the probe at `$fc4c0c` WRITES two registers and READS THEM BACK, and the kit's declared I/O map has exactly two
forms for such an address — a CONSTANT, which a store makes stale, and WRITE-THROUGH, which is what a chip that is
really there does. So every case in this group declares a machine WITH the clock fitted, and the `bcs` at `$fc5096`
that makes `gemdos_resync_clock` a no-op on a plain ST — the arm this snapshot's own machine takes — is driven by an
ORACLE claim and recorded unpinned. The kit door that would close it is a THIRD column beside
`OS_IO_DECLARED_CONSTANT`/`OS_IO_WRITE_THROUGH`: "a register a store does not reach". The RP5C15's registers are BANKED
(the probe writes in mode 9 and the digits are read in mode 8), so under a one-value-per-address map three of the
thirteen digits read back the probe's own bytes — `gemdos_process.served()` is what the cases compute their
expectations from.

**gemdos — `Pexec`'s save of the OUTER termination record has no differential, so it has TWO half-cases.** `$fc81c2`
copies the twelve bytes at `$7ef4` to `$7560` and `$fc81e0` immediately arms a new one, which is the hole
`test_gemdos_dispatch.py` measures — so nothing can span the copy. The ORACLE's half is
`test_pexec_saves_the_dispatcher_s_own_termination_record_before_it_arms_one` (stopped at the arming); the
CANDIDATE's is `test_our_pexec_copies_that_record_too`, which had to STAGE a distinctive record at `$7ef4` and a
fill at `$7560` to say anything at all — the captured machine's `$7560` already holds a byte-for-byte copy of its
own `$7ef4`, and against the snapshot alone a run that copied NOTHING read exactly like one that copied correctly
(measured: deleting the loop left the first spelling of that case green).

**gemdos — `Pterm`'s exit code in D0 at the epilogue is pinned by construction and by no surface.** On target the
epilogue's first instruction (`$fc4fee`, `move.l d0,$68(a5)`) re-stores D0 over the slot `Pterm` has just written,
and the ROM arrives there with the exit code in D0 (`$fc806c`). The reconstruction pins D0 as an input of its
`jsr gemdos_trap1_epilogue` (`src/gemdos/process.c`); unpinned, every parent on target would resume with whatever
the release loops last left there. NOTHING SEES IT: the host build returns instead of jumping, and the checkpoint
cases stop the ORIGINAL at its own `jsr`, so neither shore executes the epilogue. The surface that would catch it
is a BENCH TRANSCRIPTION case — both sides entered at a staged caller with the parent's `+$7c` frame pointing at a
stub, compared at the `rte` — and it is PARKED below rather than written, because the transcription bench enters at
a caller and a `Pterm` case would have to stage a whole second process's saved frame for it.

**gemdos — the file system's five BIOS-error arms are ONE reason in five places.** Every disk call in
`src/gemdos/fs_disk.c` ends the same way: store the result at `$75b4`, and if it is non-zero record the drive at
`$87cc` and longjmp through the process-termination record at `$7ef4` (`$fc4f54`). That record is the dispatcher's own
omission — the 68000 frame of the `jsr` that armed it — so the error arm halts on both builds and the success arm,
which is every arm a working disk takes, is reconstructed whole. The `$75b4` store is NOT part of the halt: the ROM
makes it unconditionally and so does this. `Mediach` answering 2 (a definite media change) is the same halt reached
from the other side. Two EQUIVALENT MUTANTS are recorded rather than pinned: `Mediach` asked with the DMD's `m_drvnum`
instead of the buffer's `b_bufdrv` (the hit test has just proved them equal), and `$fc50ca`'s signed compares written
unsigned. And `$fc5a98` on an EMPTY list is transcribed but unreached: the ROM reads the link of BCB 0 — the reset
vector — and would `Rwabs` through whatever `image[16..19]` holds. The DMD is a STAGED INPUT computed by the ROM's own
expressions — and since wave 9 a CHECKED one: `$fc53c0` is reconstructed and `test_gemdos_fs_drive.py` requires the
ROM's builder, run over the staged BPB, to produce the staged records byte for byte; `hdv_bpb` is exercised by `$fc67de`.

**gemdos — what a routine that reaches the BIOS still owes the harness.** Every GEMDOS call into the BIOS goes through
`gemdos_bios_trampoline` ($fc4eac): the oracle takes a real `trap #13`, whose dispatcher parks a return address at
`$eb0` and frames 46 bytes below `savptr`. The TARGET build takes the same trap, so nothing is owed there. The HOST
build cannot — there is no 68000 — and calls the BIOS core directly, which leaves two residuals: the parked longword,
which the reconstruction therefore stores itself from a named constant per call site, and the register frame, which is
neither excluded nor ignored but DECLARED — `test/gemdos.py`'s `machine()` pokes `savptr` into the run's own stack
band, so the frame lands where the differential already drops bytes and every other byte is compared as usual.
`harness._vet_exclude_bands` would refuse an exclusion here (neither band is stack, correctly), which is why the
declaration is the shape rather than a band.

**gemdos — the character devices' three halts.** `^C` in the typeahead poll ends the process through `Pterm`
(`$fc8028`, reconstructed in GEMDOS wave 2 but a CHECKPOINT case — it does not return, so a console leaf that
tail-called it would have no `rts` for its own differential either); a standard handle outside -3..-1 is refused by `console.c`'s own `per_device`,
because the ROM's six per-device tables are sized for exactly three entries in straight-line code and a fourth
indexes off all of them (it is not the dispatcher's handle-resolution arm — that one is for a handle ABOVE 0, which
the dispatcher redirects before a leaf ever sees it); and `Cauxin` inherits `Bconin(AUX:)` (`$fc2150`), which
`src/bios/bcon.c` defers for want of a staged input ring. Each halts on both builds rather than answering something
plausible.

**gemdos — the dispatcher's pop count is UNPINNED.** `call_handler`'s target build keeps the number of bytes to unwind
in D3 across the `jsr` into the handler, because D2 — where it used to sit — is scratch that a real GEMDOS leaf writes:
`Cauxout` reaches `xconout_rs232`'s `move.b $fffc00,d2`, and so do `Cprnout` and a `Cconout` of BEL. Off target the
handler is a host hook and writes no 68000 register, so no differential can see the difference; on the bench blob it
would, but every dispatcher row registered so far names a handler whose whole body is a `moveq`. Putting the count back
in D2 was measured to leave `make test`, `make guarded` and `make bench` green (only the dispatcher's own Tier 3 ratio
moves, and that is a cost pin rather than a correctness one). THE ROW THAT WOULD PIN IT is a dispatcher-SLICE case on a
character-device selector, which needs the console group's staged machine under a slice case — not written.

**gemdos — the memory manager's two honest gaps, neither of them a halt.** ONE SURVIVING MUTANT: the null guard on the
forward merge in `gemdos_md_free_insert`. No pool this harness can produce reaches it — it would take a free list whose
successor link is NULL where the list is not empty — so it is recorded unpinned rather than pinned by a fabricated
record. And the ALCYON OUTGOING-ARGUMENT SLOT: every routine in this group saves one register more than it restores
(D5/D6/D7), because Alcyon reserves the four-byte slot a callee's first argument is written into by pushing one, and
the epilogue drops it with `tst.l (sp)+`. What the arguments overwrite is that STACK SLOT and not the register — no
body here writes the register itself, which the verifier checked over all of them — so a caller's copy survives and
there is nothing for a differential to see either way.
Both ROM DEFECTS the group found are reproduced rather than corrected, with a case each: `Mshrink` writing through NULL
into the reset vectors on a spent pool, and the SIGNED grow check that lets `$80000000` past.
