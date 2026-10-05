# Reconstruction status — TOS 1.02 US

**As of 2026-09-14.** Wave 1 is merged: the ROM is bootstrapped in Ghidra, the three evaluation tiers
each have a working instrument, and the first two XBIOS functions are verified with sharp differentials.
Read `../README.md` first for the three tiers a component is held to; `test/test_status.py` pins the
counts in this file against its rows.

## Components

| component | Tier 1 (functions verified) | Tier 2 (conformance ledger) | Tier 3 (cycle ratio) | state |
|---|---|---|---|---|
| boot | 0 | — | — | NOT STARTED |
| bios | 20 | — | 0.88–3.84x, every ✅ row priced (`make bench`); one ACIA-chain routine unpriced (`acia_take_byte`, which no case enters directly) | STARTED |
| xbios | 29 | — | 0.23–2.03x, every ✅ row priced; the shared timer programmer unpriced (register arguments), and Scrdmp (entered only through the VBL and v_hardcopy's `trap #14`) | STARTED |
| gemdos | 109 | — | 0.35–1.79x, every ✅ row priced; the three terminators verified and unpriced (they stop at a CHECKPOINT, so there is no second column) | STARTED |
| vdi + linea | 151 | — | shipped code 0.36–1.52x (`vq_key_s` 1.52 and `vdi_choice` 1.49 accepted at their shipped numbers); 48 ROM routines ship as byte-exact `.S` at 1.00 (their C carried by (T)), the escape's `.S` rows that reach the BIOS console's C through its own thunks 1.31–2.43x as shipped, verdict `own` (T←: its own instructions within the bar, the console's C carried by five cited Bconout(CON:) acceptances); every C caller of a transcribed core measured AS IT SHIPS (T→ `through`, 0.42–1.10), fourteen rows over the bar as shipped carried by the DERIVED glue rule (T→G `glue`, 1.10–2.05 shipped, 0.69–1.08 net of the thunks); the GEMDOS-trap rows priced over a staged `trap #1` with LINEA_RETSAV dropped by name | COMPLETE but the deferred BLITTER bodies |
| aes | 291 | — | shipped C 0.10–1.10x (the worst two AT the bar: `dos_alloc`'s failure arm, 1.0993, an image-relative store, and `gsx_tcalc`'s empty string in the small font, 1.097, through xstrpix's glue); 35 ROM routines ship as ONE byte-exact `src/aes/optimize.S` at 1.00 (their C carried by (T), 1.11–2.78), five of gemgsxif's Line-F-free atoms as `src/aes/gsx.S` (C 1.20–2.21, (T)), four more as `src/aes/gsxif.S` (gsx_mret, ratinit, gsx_mxmy, gsx_button: C 1.46–1.81, (T)) and five of gemgraf's as `src/aes/gemgraf.S` (gr_inside, gr_crack, gsx_gclip, gsx_chkclip, gsx_bxpts: C 1.44–2.07, (T)) and gemdosif's uda_insuper and psetup as `src/aes/pdpipe.S` (C 1.50 / 1.24, (T)); every row whose C reaches the VDI by `trap #2` priced on its OWN cycles (V: 0.20–1.07 against the ROM's AES text and Line-F handler, the OS both run in neither; 17 of them `glue`, 1.10–1.28 with their thunks); every row whose C reaches the event layer through THE EVENT DOOR priced net of its door windows (EV: 0.27–1.04; since band 4 wave 0 the door's first entry, tak_flag, is REBOUND — its C twin on both builds, each call an ARRIVAL with no window, the ROM's routine in the ROM's own cycles: 88 rows moved by it, none over 0.82 — gr_stilldn, gr_watchbox (V+EV), ap_sendmsg; band 3 wave 1's window update, screen lock, drag loops and menus 0.27–0.82; band 3 wave 2's forms and alerts 0.29–0.87 over a sixth door entry, ev_button; band 3 wave 3's file selector, fs_input, 0.62–0.96 by the SLICES of six sessions and 0.73–0.77 on its three no-memory arms; the rows taken THROUGH INTERRUPTS (55, 0.58–0.96 — 39 of them SLICES of seven sessions too long for one row, each the run between two arrivals both shores make at one PC, our memory held to the ROM's at both) priced the same way, their deliveries laid at the same door calls on every run of both sides — our run watched at the door's entries, the original's watched too, both sides' windows equal cycle by cycle and frame by frame); just_draw's ALCYON ENTRY `src/aes/obdraw.S` — the routine the target ob_draw hands everyobj — target-only glue, its cycles counted as glue (T→G: ob_draw 0.75–0.89 own, 0.88–1.01 with it), and newrect's and mkrect's in `src/aes/wmupdate.S` (draw_change's walk) the same way, gsx_moff's open nest (1.23) and gsx_graphic's mode held (1.24) accepted (A); every C caller of a transcribed core measured AS IT SHIPS (T→ `through`, 0.12–1.10); every ✅ row priced over a direct `jsr` (the Line-F handler's self-patched mask word `$cc44` dropped by name, each drop with its undropped companion), the three >6-argument cores (ob_sst, everyobj, inf_fldset) entered with our side's stack pointer lowered by what does not fit; each routine's Line-F-entered case verified and unpriced; the selector's rows that reach GEMDOS priced over GEMDOS REPLAYED (the ROM's own answers and DTAs, call by call, every frame in a ledger the differential compares); `dos_free`, `dos_sdta`, `dos_close` and the bell's Cconout glue verified and unpriced (a host argument) | STARTED — bands 0+1: the LEAVES and the OBJECT/RESOURCE layer; band 2 wave 1: the `trap #2` bridge and gemgsxif's atoms, shell find + resource load, newrect; band 2 wave 2: the rest of gemgsxif (the `$a000` bridge), gemgraf and gemgrlib's non-interactive animations; band 2 wave 3: the object draw path (ob_format, far_call, ob_user, just_draw, ob_draw, ob_change) — BAND 2 COMPLETE; band 3 wave 0: THE EVENT DOOR with its pilots (gr_stilldn, gr_watchbox, ap_sendmsg, ct_mouse), the object editor (ob_edit and its ten helpers) and the window library's pure half (23 routines); band 3 wave 1: the window messages and update with the screen lock (13 routines), the interactive gemgrlib and the menu library (16), five more door entries and interrupts delivered at door entries; band 3 wave 2: the forms and the alerts (gemfmlib, gemfmalt, the keyboard-queue leaves fq / dq and fm_do's bell — 16 routines), ev_button the sixth door entry, the interrupted rows priced and fully vetted, keys delivered through the BIOS keyboard handler; band 3 wave 3: the file selector (gemfslib's nine event-free routines and fs_input run whole as sessions, dos_snext and the bell's Cconout glue — 11 routines and one unpriced), a case's own derivation budget, sessions priced by their slices with the partition held, GEMDOS replayed — BAND 3 COMPLETE; band 4 wave 0: the event door made REBINDABLE and tak_flag rebound (flip 1 of three), gemasync's lists with evremove (8 routines), the PDs and the pipes (9, two of them shipping as `.S`), a third process as the labelled STAGED APPLICATION (Tier 1 only) |
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
| `0xfc4698` | `Cursconf` (XBIOS $15, `src/xbios/cursconf.c`) | 30 | 10 / 144 blink, 11 / 144 get rate, 132 / 1318 hide, 143 / 1448 show | **1.65** blink, **1.33** get rate, **1.36** hide, **1.47** show | ✅ verified | the six RAM arms plus the out-of-range return, each at its truncation boundaries (the two that DRAW are the sentence at the end of this cell); what each arm leaves in D0 read OUT OF THE ROM's jump table rather than written down ($0010/$0016/$001c for the arms that set no result); the rate and the spare proved to be different bytes; and the WIDTH — the caller's high half surviving the `move.w` arms and cleared by the `moveq #0,d0` ones. Arms 0/1 are the console's own cursor renderer and no longer halt: they call `console_hide_cursor`/`console_show_cursor` ($fc45d8/$fc45be), and `test_bios_vt52.py` drives each over both a cursor that is on screen and one that is not, with the dispatch's displacement still the result. |
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
| `0xfc0d50` | `Scrdmp` (XBIOS $14, `src/bios/vbl.c`'s `xbios_scrdmp`) | 7 (3 VBL + 3 v_hardcopy + the table entry) | — | — | ⚠️ verified, unpriced | the VBL's Alt-Help dump arm IS this body (band 4 exported the old static `screen_dump`): through the VBL (`_dumpflg` set calls nothing; cleared calls `scr_dump` ONCE and sets the flag again; the routine `scr_dump` names and not a decoy) and through v_hardcopy's real `trap #14` (flags 0 / 1 / $ffff), each over a RECORDING `scr_dump` (`isr.flag_recorder`) that reports `_dumpflg` as the routine finds it and counts its calls — the review's two surviving mutants (flag set before the call, called twice) are killed by either battery alone; `XBIOS_SCRDMP` read out of the ROM's XBIOS table at number 20. UNPRICED because no case enters `$fc0d50` itself; its cost is inside the escape's v_hardcopy rows |

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
| `0xfc099c` | `Bconout` (BIOS $03, `src/bios/bcon.c` + `src/bios/vt52.c` + `src/bios/conout_glyph.c`) | 263 (60 + 196 in `test_bios_vt52.py` + 7 in `test_bios_console_bus.py`) | 13 / 182 midi, 2867 / 42038 ikbd, 213 / 2962 printer, 15 / 234 printer held off, 25 / 342 rs232 ring only, 58 / 762 rs232 primed, 7 / 116 no driver, 235 / 2308 console glyph, 357 / 3492 console glyph with the cursor, 61 / 756 console line feed, 10284 / 180834 console scroll, 14006 / 166532 console clear to end of screen, 19 / 252 console escape state, 231 / 2260 raw console | **1.01** ikbd, **1.03** console scroll (pinned UNDER the bar), **1.04** printer, **1.43** rs232 primed, **1.49** console clear to end of screen, **1.71** console glyph with the cursor, **1.85** raw console, **1.87** rs232 ring only, **1.93** console glyph, **1.96** printer held off, **2.23** console line feed, **2.82** midi, **3.24** console escape state, **3.84** no driver (the rest accepted; see `bench/tier3.py`) | ✅ verified | the table walk AND every driver it jumps into. The two 6850 senders: the low byte of the character word on each data port, the poll as a DECLARED SEQUENCE (busy, then ready) in the ordered stream, and the dispatch's own scratch back in D0 — the same answer a device with no driver gives. The printer: the whole YM2149 send as an ordered chip ledger (mixer read, port B turned into an output, the byte, then the strobe LOW TWICE and HIGH, each a `Giaccess` read-modify-write), the BUSY wait round a declared sequence, the five-second hold-off's UNSIGNED compare proved by a failure stamp AHEAD of the clock, the thirty-second timeout reached through a SCHEDULED 200 Hz tick at its exact boundary and one tick short, its `blt` proved SIGNED by a clock half the longword range on — and the SERIAL REDIRECT, which is a BYTE test on a WORD field and so reads bit 12: `$0010` prints and `$1000` redirects. The RS232: the byte into the output ring at the ADVANCED tail with the ROM's wrap-at-size at both boundaries, a busy transmitter left alone, an idle one handed the byte straight back out of the ring, the flow-control pair ANDed over four combinations, an XON jumping the queue and being cleared, and three layers of D0 — the caller's high half, the character's high byte and the flow byte's low one. The console: the six-state machine at $4a8 (normal, escape, ESC Y row/column, ESC b, ESC c), the control codes $07..$0d (BEL trap-free through conterm bit 2 and the $fc31c2 sound list; VT and FF the same table entry as LF), every escape the ROM's three jump tables really implement (A B C D E H I J K L M Y b c d e f j k l o p q v w; F G g h i m n r s t u are table entries pointing at a bare rts), the cursor lock as a DEPTH whose unlock leaves the depth in D0 (so `ESC l` puts the cursor in column `depth`, swept at four depths), the horizontal/vertical escapes' differing D0, the spare byte $2995 that is not spare, the four screen routines reached through RAM vectors (CPU set reconstructed; the blitter set halts), a group being `1 << (planes >> 1)` words for the clear and `planes` for the glyph. And (band 4) the CELL ADDRESS ON THE 24-BIT BUS: an ESC Y row byte below the $20 bias forms an address past 16 MB that the ROM wraps to the row above the screen, where the host aborted — a LATENT divergence, fixed by `vt52.h`'s `console_screen_block` (form, wrap, then bound) for every console screen writer and pinned by `test_escape_y_with_a_row_byte_below_the_bias_wraps_on_the_bus` (depth 0 and 1) and `test_bios_console_bus.py` (glyph → ESC → K chained, the RAW glyph, the escape's placements); target objects byte-identical, no Bconout row moved. Mutation 21/21 |
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

## Verified — gemdos (109)

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
| `0xfc973e` | `gemdos_dispatch_selector`, the arms PAST that record (same file) | 106 | 604-640 per dispatched selector; 682-47466 the arms | **0.78**-**0.80** dispatched; the arms **0.90**-**1.08**; **1.71** (accepted) an empty redirected `Cconws` | ✅ verified | `test/test_gemdos_dispatch.py` (48) as before — six selectors dispatched through our own leaves, every descriptor class's frame read off the ORACLE's stack, the descriptor REWRITE (now pinned on the candidate side too), the HANDLE-RESOLUTION arm (`$fc9924`) whole — plus the three arms that serve a call WITHOUT its handler, all reconstructed: REDIRECTED (`$fd328a`, `test_gemdos_dispatch_redirect.py`): Cconin & co. through Fread (EOF answers the stale `-14(a6)` byte — a TARGET DIVERGENCE, pinned off target only), Cconout & co. through Fwrite with the ROM's BROKEN buffer pointer `(char<<16)|$7ef4` folded onto the 24-bit bus, Cconws (an empty string answers the jump's own D0), Cconrs with a SIGNED maximum and each byte echoed through a nested dispatch (the `$7ef4` record span it re-arms DROPPED from the compare by name — the C leaves the record untouched), status always $ff; DEVICE (`$fc99bc`, `test_gemdos_dispatch_device.py`): Fread of one byte / a line, Fwrite through the TAB expander or Bconout, a count with a high word answers 0, Fseek answers 0 — the SHORT rows registered (1-byte AUX: 1.08); DEVICE-NAME (`$fc9aca`): six names, five bytes each, answered as an unsigned word ($0000FFFF…), and a name pointer with a TOP BYTE read through the 24-bit bus (`gemdos_strneq`'s `bus_byte`). Unpinned: a negative selector's redirect bound; Crawio's dead entry and 12..15 (a named halt); Cconout of a character past 1 MB or on the I/O page. Mutation 69/71 |
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
| `0xfc91ea` | `Cconrs` (GEMDOS $0a) | 15 | 38-3986 / 538-48330 | 0.86x, 0.88x, 0.91x, 0.92x, 0.94x | ✅ verified | every key the ROM's own two nine-entry tables implement — BS and DEL one arm, LF and CR one arm, ^R, ^U, ^X — the ninth (zero) key sharing the DEFAULT arm, the erase MEASURING the line (a TAB taken back whole, a control code two columns), both buffer bounds (a maximum of 0 reads no key; a full line leaves the next key queued), and the length written back with nothing terminating the text |
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
| `0xfc817a` | `Pexec` ($4b, same file) | 14 | 10 / 144, 13341 / 182322 | **1.79** (accepted), **0.86** (T→) | ✅ verified | the mode bound at both ends of the GAP that 1 and 2 are and every word above 5 incl. both sides of the sign, with nothing stored (accepted: three argument spills the compiler hoists above the mode test, ~84 cycles ≈ the whole excess); the FILE LOOKUP `sfirst(name, 0, no DTA)` before anything is cut — a missing name, a missing directory and a HIDDEN or SYSTEM program all EFILNF, pool and handle table untouched. The record it saves to `$7560` is an ORACLE claim; the one it arms is the hole `$fc973e`'s row measures |
| `0xfc8242` | `gemdos_pexec_create`, `Pexec` past that record (same file) | 56 | 2808 / 41188 mode 5, 15949 / 219840 relocated, 21971 / 303546 in chunks, 13775 / 186736 not a program | **0.38**, **0.72**, **0.77**, **0.70** (T→ through `clear_span`'s `.S`) | ✅ verified | MODE 5 whole: the TPA as the WHOLE largest free block, the clear running eight bytes past the basepage (both ends of the overrun pinned), the environment measured to its double NUL and rounded at three lengths, an env pointer of 0 taking the parent's, the tail at four lengths incl. one past 125, device handles copied and a FILE `Fforce`d, all sixteen directories inherited zero or not, and both ENSMEM arms — the spent POOL, and a largest block below 256 with the environment given back. MODE 4: it touches no allocator at all, and builds the child's stack, `p_parent`, and A4/A5 from the segment bases. MODE 3 end to end over synthesised PRGs on the staged disk (the whole TPA and basepage compared); a failed load RELEASES THE CHILD and answers the loader's word sign-extended — and since mode 3 charged the TPA and environment to the CALLER both stay allocated (a leak, pinned) with the file left open. MODE 0: a checkpoint at `$fc85c8` with the relocated program, the child p_run and its entry; a failed mode-0 load frees both (charged to the child) |
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
| `0xfc6fdc` | `gemdos_ofd_open` (same file) | 20 | 457 / 6748 | **0.44** | ✅ verified | first open takes the entry; a second open copies 12 bytes from +6 (two into OFD_DMD) and sets the first's OFD_NEXT_SAME_FILE; ENSMEM stores nothing |
| `0xfc6f5c` | `gemdos_handle_alloc` (same file) | 5 | 408 / 6060 | **0.49** | ✅ verified | free = OWNER 0, not value 0; ENHNDL at 75 owned; ENSMEM passes through with the record left claimed (count 1) |
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
| `0xfc53c0` | `gemdos_dmd_build` (same file) | 11 | 1331 / 18804 | **0.52** | ✅ verified | eight geometries (the staged disk, 720K, FAT16 with every other BFLAGS bit, one sector per cluster, a 1000-byte sector, recsiz 0 reading the word BELOW `$fd2fc8`, a negative rdlen `muls`, a negative quotient `divs`) and ENSMEM; the BPB read in the ROM's ORDER — `fatrec` twice after the stores (a BPB under the DMD being cut); the staged `gemdos_fs.drive()` PROVED equal to what the ROM builds, which found the FAT pseudo-file's start at position 3 / byte 3 ($fc55be) the staging lacked. Unpinned: a zero `clsiz` (`divs.w` by 0, vector 5 — the host REFUSES); the root name `clr.b` over a pool-cleared record (equivalent) |
| `0xfc67de` | `gemdos_open_drive` (same file) | 15 | 1436 / 20260 log-in, 29 / 400 logged in | **0.55**, **0.95** | ✅ verified | log-in through the staged `Getbpb` (the first caller `hdv_bpb` has had) + the builder + the mask bit; `Getbpb` 0 → ERROR and ENSMEM with nothing kept; `asl.w` semantics (drive 15 = the sign bit, 16 = no bit, -16 = shift 48); every table index SIGNED incl. the curdir byte; a dead or absent curdir replaced by the first zero count from 1 (slot 0 skipped even when free), the old count NOT dropped; forty held → ERROR |
| `0xfc68dc` | `gemdos_path_start` (same file) | 12 | 75 / 964 | **0.98** | ✅ verified | `X:` (upper-cased, `'A'` subtracted as a word: `1:` is drive -16), a leading `\` → root, otherwise p_curdir's node; the current drive SIGNED; a new drive logged in underneath; a drive that will not open → 0 with the pointer NOT stored; the empty path reading past its NUL. Unpoisoned (the pointer is chased) |
| `0xfc7e52` | `gemdos_dot_name` (same file) | 13 | 34 / 376 | **0.66** | ✅ verified | "" = `moveq #1` (the whole register), "." -1 and ".." -2 only when the TERMINATOR follows, "..." / ".X" / "..X" ordinary, a terminator of '.' making ".." SELF, the terminator's low byte alone compared; the caller's high half on every other answer |
| `0xfc5e08` | `gemdos_split_path` (same file) | 12 | 364 / 3810 | **0.57** | ✅ verified | the tail NOT taken without the flag (tested BEFORE the dots, so ".." as a tail is 0), -1/-2 with nothing built, a zero-length component building nothing, and the three high halves of D0 — the caller's, 0 after a build, 0 after `$fc7e52`'s empty answer |
| `0xfc7e94` | `gemdos_strneq` (same file) | 10 | 74 / 850 | **0.47** | ✅ verified | STANDALONE (its caller is the dispatcher's device-name arm, a later band): no NUL stops it, a count of 0 is equal, case-sensitive, bit-7 bytes, and 0 over the caller's high half on a miss |
| `0xfc663c` | `gemdos_dir_search` (`src/gemdos/fs_dir.c`) | 40 | 3957 / 49972, 6194 / 84734, 4497 / 57726 | **0.75**, **0.82**, **0.81** | ✅ verified | first match (wildcards, attributes, only the low attribute byte); runs to the end and marks it OFD_SCANNED; an `$e5` search reuses a deleted entry or takes the end-of-directory entry unmarked; a directory ending with its chain; its OFD made on first use; DNDs made for every subdirectory passed beyond the SIGNED mark (from position 0 and, from the mark, raised SIGNED from −32); the known-name arm along the WHOLE child list; from the mark it answers the LAST DND MADE and un-reads the found entry; a spent pool at both requests |
| `0xfc696c` | `gemdos_find_dir` (same file) | 15 | 9084 / 111134, 1792 / 20484 | **0.75**, **0.72** | ✅ verified | two levels, take_tail on a directory and on a file, `.`/`..` climbing and reuse, staged DNDs with no disk read, the child list walked PAST its head (the common walk), `..` off the root, the tail left AT or PAST a missing component by miss kind, the end flag, the current directory, a drive that will not open. `tst.l a4` at $fc6a00 dropped (unreachable) |
| `0xfc6df4` | `Fsnext` ($4f, same file) | 5 | 2080 / 25596, 5985 / 74346, 5532 / 73344 | **0.88**, **0.84**, **0.83** | ✅ verified | the DTA's unaligned position/DND byte-wise; the next match with the DTA filled; across a cluster making the DNDs it passes; ENMFIL with the DTA untouched; a DTA position of −1 filling the DTA from a DND; the dispatcher slice |
| `0xfc57ee` | `gemdos_ofd_close` (`src/gemdos/fs_file.c`) | 11 | 6076 / 71088, 1591 / 19672 | **0.98**, **0.94** | ✅ verified | clean and dirty (cluster and length turned round in the OFD and back, time/date as stored, OFD_DIRTY never cleared); flag 2 writes length 0 and does not unlink, 6 does (`btst #2`); unlink at head, middle and tail; EINTRN before the flush; every buffer of every list flushed (dirty written and kept, clean EMPTIED) |
| `0xfc7824` | `gemdos_delete_entry` (same file) | 9 | 9178 / 116440, 34 / 564 | **0.97**, **0.82** | ✅ verified | a three-cluster chain, one odd cluster, cluster 0; the `$e5` mark and the flag-2 directory close flushing FAT and root; EACCDN for another process's open, after the caller's earlier handles were closed (and never released); an open file at another position ignored; the caller's second close of one OFD is unobservable (unpinned) |
| `0xfc772e` | `Fdatime` ($57, same file) | 7 | 1535 / 18760, 6023 / 70294 | **0.96**, **0.99** | ✅ verified | read (handle record and standard handle; D0 = the swapped date over the count), a NULL buffer answering the cache pointer's high half, write leaving the caller's buffer swapped, the slice; NO OFD check — the NULL-OFD arm halts here (oracle-only claims: GET swaps only the caller's buffer, SET never returns) |
| `0xfc7a68` | `Dfree` ($36, `src/gemdos/fs_leaves.c`) | 10 | 12401 / 175344 | **0.96** | ✅ verified | clusters 2..m_numcl−1 scanned, the two past the scan staged FREE and not counted; from cluster 2; the current drive; FAT16 incl. a used entry with a zero low byte; a new drive logged in; −1 for ENSMEM and a bad drive; the slice |
| `0xfc6c1a` | `Dgetpath` ($47, same file) | 6 | 291 / 3590 | **0.93** | ✅ verified | NUL over `$fc6bd2`'s last `\` (the root as ""), two levels, the current drive, EDRIVE with the empty string, the slice |
| `0xfc6d14` | `gemdos_sfirst` (`src/gemdos/fs_open.c`) | 2 | 3293 / 41986 | **0.82** | ✅ verified | the attribute WORD widened by $21 unless exactly 8; either miss EFILNF; the DTA filled from the path's 12-byte tail (caller bytes past a short name's NUL leak in), the widened attribute byte, the unaligned position and DND, then fill_dta; dta 0 searches and stores nothing (Pexec's use). The dead `tst.l` at $fc6d4a not kept |
| `0xfc6cf6` | `Fsfirst` ($4e, same file) | 18 | 12383 / 153320, 6479 / 88222 | **0.76**, **0.82** | ✅ verified | through p_run's DTA: widening (VOLUME alone not widened, a high-byte word widened, a read-only file found only because of it), hidden, lowercase and `?`, two levels down, a root child list three long, five misses with the DTA untouched; Fsfirst→Fsnext chained through `gemdos_fs.continued` (a real differential: both shores start from the carried state) to ENMFIL, in the root and in INNER; the dispatcher slice |
| `0xfc6a7e` | `Dsetpath` ($3b, same file) | 14 | 9082 / 111296, 6649 / 90030 | **0.75**, **0.82** | ✅ verified | the old node's count dropped FIRST and never restored on EPTHNF (sole and shared holders); the slot search after the drop (a sole holder's node comes straight back only when no lower slot is free); slot 0 skipped; `X:` picks the drive for the log-in but the walk runs on the CURRENT drive — and the walk's own log-in can take the slot just chosen (two drives share one node, count 2); a bit-7 letter is a negative drive whose log-in answer reads as an error; a signed p_curdir byte; forty held nodes EPTHNF before the walk; the slice. The 0-byte skip at $fc6adc is unreachable |
| `0xfc7606` | `gemdos_open` (same file) | 1 | 3697 / 46614 | **0.74** | ✅ verified | searched under $27 (never a plain subdirectory or the volume label); EFILNF for either miss (a missing DIRECTORY too); EACCDN for a read-only entry opened with any non-zero mode WORD, before a record is claimed; the mode word stored whole by handle_alloc |
| `0xfc75f2` | `Fopen` ($3d, same file) | 18 | 12589 / 155800, 3797 / 48010 | **0.75**, **0.80** | ✅ verified | modes 0/1/2 and high-byte mode words; two levels down; a list three long; a second open sharing the OFD found SECOND on a two-long files list; ENHNDL; ENSMEM with the record already claimed. the dispatcher slice (past the device-name arm) |
| `0xfc7678` | `Fattrib` ($43, same file) | 19 | 8140 / 110144, 8129 / 97258 | **0.78**, **0.91** | ✅ verified | one byte 21 behind the search position moved through the directory's OFD into or out of the argument's own low byte (host slot ATTRIBUTE); get with no flush; set with the flag-2 close flushing everything; NOTHING checked (read-only cleared, any byte incl. the subdirectory bit, a directory reached through its ARCHIVE bit); EPTHNF vs EFILNF; answer = `ext.w` of the byte over a D0 high half 0 on every reachable arm (equivalent) |
| `0xfc77b2` | `Fdelete` ($41, same file) | 11 | 11651 / 148724, 3357 / 41576 | **0.92**, **0.78** | ✅ verified | $27 search; EFILNF for any miss; read-only EACCDN before anything is touched; delete_entry one entry behind the position: chains of 1 and 3 clusters freed and `$e5` on the disk, two levels down, a list three long, another process's open EACCDN, the caller's own open closed; the slice |
| `0xfc71b6` | `gemdos_create` (`src/gemdos/fs_create.c`) | 22 | 12573 / 171602, 14924 / 191688, 59282 / 802062 | **0.82**, **0.91**, **0.85** | ✅ verified | an existing entry DELETED through $fc7824 (not truncated) and its slot reused, the delete's answer IGNORED — a file another process holds gets a SECOND entry of the same name; only read-only or subdirectory refuse (`and.w #17`), a volume label replaced; a full root and a full disk EACCDN (the root cannot grow); a subdirectory grows by a zeroed cluster; a spent pool makes the root look full; the entry written in the cache, ENHNDL after it is on disk. ENSMEM via $fc6f5c unpinned (the ENHNDL arm) |
| `0xfc719a` | `Fcreate` ($3c, same file) | 5 | 12583 / 171736 | **0.82** | ✅ verified | the attribute byte `ext.w` then `and #$ef` (subdirectory bit masked), high-byte words. the dispatcher slice |
| `0xfc792a` | `Ddelete` ($3a, same file) | 16 | 17079 / 219182, 10378 / 127160, 5850 / 71178 | **0.85**, **0.94**, **0.79** | ✅ verified | non-empty EACCDN (the root refused only by its scan, which skips two entries); EINTRN for a child DND and for open files, BOTH reached by real call chains (the second needs duplicate DNDs: any position-0 search makes a fresh DND for each subdirectory it passes, because only the walk moves DND_SCANNED); NO current-directory check; the made OFD leaks; fields read from the freed OFD. Unpinned: an EMPTY root never returns (oracle-only claim; the C halts); a DND its parent does not list |
| `0xfc73ce` | `Dcreate` ($39, same file) | 10 | 33395 / 437942, 37866 / 483802, 32181 / 443180 | **0.78**, **0.78**, **0.95** | ✅ verified | `.`/`..` from the ROM templates $fd2fec/$fd3002 with the clock NOT swapped; `..` 0 for the root, the parent's cluster two levels down; the 50-byte OFD copy + close(6) unlinks every OFD opened earlier in the parent; ENSMEM paths leak the file and handle; a full disk rolled back through Ddelete |
| `0xfc7af0` | `Frename` ($56, `src/gemdos/fs_rename.c`) | 26 | 13139 / 175492, 23242 / 300510 | **0.79**, **0.83** | ✅ verified | the NEW name searched first (`sfirst` attr 0 → $21, no DTA), so a hidden, system or directory entry of the new name is unseen: an in-place rename DUPLICATES it, a move REPLACES a system file; EPTHNF ×2; ENSAME compares the two DMDs' drive WORDS; `Fopen(old,2)`'s errors returned. In place: 11 FCB bytes over the entry. A MOVE: `$e5` over the old entry (chain NOT freed), its 10 tail bytes kept, `Fcreate(attr)` UNCHECKED, the tail written over the new entry, the new OFD made clean, closed, its directory closed through the freed OFD — the chain changes hands with no FAT traffic. A refused Fcreate is read as a handle (p_tlen byte 0 → record 0): the old file loses its name and Frename answers 0; when another open file holds record 0 the tail lands in ITS entry and its OFD is made clean (real chain). A write through a handle still open is lost by the move. Dispatched slice. Unpinned: p_tlen ≥ 64 KB; `Fclose(old) < 0` (unreachable). Mutation 30/36 (4 equivalent, 1 unreachable, 1 crash-only) |
| `0xfc85ea` | `gemdos_pexec_load`, Pexec's loader and relocator (`src/gemdos/pexec_load.c`; `$fc4b7c`'s span clear now lives in `src/vdi/screen.c`/`.S`) | 47 | 13135 / 178590 | **0.79** (T→ through `clear_span`'s `.S`) | ✅ verified | 20 synthesised GEMDOS-format PRGs on the staged disk. The `Fopen` mode is the CALLER'S D5 HIGH HALF (the loader pushes only the name over its own saved D4) — pinned against the ROM trap entry's own frame; magic only (else EPLFMT); NO `Fread` answer checked; the BSS fit a SIGNED compare before any read; bounds only at the first fixup (signed low, unsigned high) and at chunk boundaries — in-chunk fixups UNCHECKED (pinned past the TPA); a first offset of 0 means no relocation; the stream read in chunks into the TPA past DATA; the WHOLE TPA past DATA cleared; the absolute flag skips relocation, clear and close; program flags ignored; an overclaimed symbol table's Fseek ERANGE ignored; the file LEFT OPEN on every error after the open; the short-file stale `-38(a6)` local staged explicitly (oracle claim). Unpinned: a ≥32 KB stream's word truncation; odd fixups (address error); the clear's runaway from a negative BSS length (reachable, not staged). Mutation 40/44 (3 equivalent, 1 unpinned) |
| `0xfc93f4` | `gemdos_free_dnd_tree` (`src/gemdos/dispatch.c`) | 3 | 1651 / 15424 | **0.53** | ✅ verified | STANDALONE, ahead of its caller the E_CHG recovery (behind the longjmp): child tree, sibling tree, the directory OFD, every node slot naming it, then the DND — the pool chain's order the witness; a subtree takes its later siblings. Mutation 7/7 |
| `0xfc9468` | `gemdos_free_drive_ofds` (same file) | 3 | 839 / 10396 | **0.41** | ✅ verified | STANDALONE. ROM BUG: the pushed argument is never loaded — the OFD's DMD is compared against the CALLER'S A4; frees the records naming OFDs on it (value, owner and refcount), passing over devices, the table's last record reached. Mutation 6/7 (1 equivalent) |

THE THREE DISK ROWS' ~1.00 IS A RATIO OF THE WHOLE CALL AND NOT OF THE CORE, and it is worth reading
that way. `gemdos_buffer_flush`, `gemdos_buffer_get` and `gemdos_rwabs_data` each end in a `Rwabs`
through the STAGED 68000 driver, whose byte copy is 512 × 22 cycles — about 11k of each ~13k column,
identical on both shores. The core's own share is ~1-2k, so a change to it moves the printed ratio by
a fraction of what it moved the core by, and these three rows are a weaker instrument than their
figures suggest. NETTING THE STUB OUT (a per-row `staged_entry` measured from a zero-count `Rwabs`)
is a bench change and is PARKED below.

## Verified — vdi (151)

The VDI + Line-A component (`$fc9f0c..$fd2f21`, `src/vdi/`), started 2026-09-26 on a read-only map of the whole range and a
FOUNDATION every band builds on: `include/vdi/{linea,vdi,font}.h` (every field cited to a ROM access and TAGGED with its width,
which is what `test/vdi.py`'s `FIELDS` parses), `test/vdi.py` (the one staging door: records by name, a workstation staged AS THE
DISPATCHER LEAVES IT — record plus its 21 copies into Line-A, pinned against the ROM's own dispatcher — pokes merged byte by byte,
the screen and pixels, `run_function` / `declare_primitive` + `run_primitive` / `run_through_exception`, `register`). DECISIONS
(the user's): the hand-written 68000 pixel loops are ported to C first and fall back to a byte-pinned `.S` transcription only where
the C measures over the 1.10 bar; the BLITTER bodies are deferred (see `## Not reconstructed`).

| address | function | cases | original insns / cycles | Tier 3 | state | what the cases pin |
|---|---|---|---|---|---|---|
| `0xfcb45c` | `vsf_perimeter` (VDI opcode 104, `src/vdi/vdi.c`) | 10 | 16 / 314 outlined, 17 / 322 not outlined | **0.72** outlined, **0.70** not outlined | ✅ verified | the VDI's worked example, entered as the dispatcher's `jsr` leaves the machine, over a DISPATCHED workstation (record + the dispatcher's copies): six intin words incl. $0100 and $8000/$ffff, stored normalised to 0/1 in intout[0] and `WS_FILL_PER` over a stale $5a5a; the workstation written is the one `LINEA_CUR_WORK` names (a virtual one, the physical record untouched); contrl[4] = 1 written LAST, pinned by laying intout over it. Opcode 104 read out of the ROM's table. Mutation 10/10 |
| `0xfc9f34` | `$a000` linea_init (Line-A, `src/vdi/linea.c`; SHIPS as `entry.S`'s `linea_rom_init`, band 4) | 3 + 1 `.S` | 6 / 96; `.S` 12 / 180 by `jsr` | **2.43** (T `transcribed`); `.S` **1.00** | ✅ verified | the primitive doors' example: D0/A0 = the Line-A base, A1 = $a000's font table, A2 = the opcode table, EACH compared register by register on both shores (Tier 3's column holds D0: the core returns it); entered by `jsr` and — unpriced, entered at a stub — THROUGH the Line-A exception, where the handler preserves D3/A3 and the `rts` after the opcode word is reached. Band 4: the C is now a `TRANSCRIBED_CORE` and ships as `entry.S`'s `linea_rom_init` inside linea_dispatch's pinned region, answering its OWN tables (the `.S` row by `jsr` through a caller pool that clears A1/A2; contract `a2`); the (N) acceptance is DELETED, which `test_no_transcribed_c_row_carries_a_written_acceptance` requires of a (T) row. Mutation 3/3 |
| `0xfc9f0c` | `$Axxx` linea_dispatch (the Line-A exception, vector $28, `src/vdi/entry.c`; SHIPS as `entry.S`'s `linea_rom_dispatch`) | 9 + 6 `.S` | `.S` 26 / 480 $a000, 66 / 930 $a001, 74 / 902 $a002, 293 / 3380 $a007 one pixel, 14 / 222 unserved | `.S` **1.00** on all six rows ($a000, $a001, $a002, $a007 one pixel, $a010 and $afff unserved); the C twin verified and unpriced (entered at a staged frame) | ✅ verified | the C twin entered directly on an exception frame staged in COMPARED image (a trampoline puts SP on it, so the stepped PC it writes back is compared; the handler's own pushes dropped by `dropped_windows`, poison off — it reads the pointer it writes): the opcode word read and the PC stepped past it (that order is UNPINNED — it would show only for an $Axxx word lying in the frame's own PC slot, and staging that makes `rte` resume onto the sentinel); the mask $fff ($a100, $a800 and a staged $f000 word); 0..15 served through the table (incl. $a00f, the contour fill with a seed above the clip, the last it serves), 16+ ($a010, $afff) only the PC stepped; D0/D1/A0 through the register hook into the primitives' C cores. `entry.S` is ONE byte-pinned region `$fc9f0c..$fc9ffb` (this, `$a000` and vdi_entry) with 16 declared words: `$a000`'s two `lea`s of its own tables and the 14 table longwords whose primitive ships as `.S`, each relocated to that entry's address in the blob; `$a009` (v_show_c) and `$a00f` (the contour fill) ship as C and keep the ROM's addresses, and a test pins that exactly those two lie outside every pinned region; the ROM's own encodings spelt as `.word`s through `M68K_*_IMMEDIATE`. Register contract `d2 a2 a6` — a door is charged the union of what it serves, and the A6 the review found MISSING (`$a007` adds 76 to A6, `$a00d` loads it; the case choice had hidden it) is measured through the `$a007, one pixel` transcription row, which reds the old `d2 a2`. Residual: the C twin hands a primitive D0/D1/A0 only and cannot show D2 or the `movem` bracket. Mutation: the Line-A arms in vdi_dispatch's sweep, all killed; the `.S` is held word for word by the byte pin |
| `0xfc9f9e` | vdi_entry (`trap #2`'s VDI arm, `src/vdi/entry.c`; SHIPS as `entry.S`'s `vdi_rom_entry`) | 19 + 6 `.S` | 84 / 1632 no points, 93 / 1714 one point, 2140 / 24226 the cap | **0.94** no points, **1.02** one point, **1.68** the cap (T `transcribed`); `.S` **1.00** ×3 (0, 1 and 513 points) | ✅ verified | the five pointers read and stored in the block's order (the block laid at LINEA_BASE, so each is read after the store before it); the count read AFTER the stores (contrl at LINEA_CONTRL+2); 2n formed in a WORD and capped UNSIGNED at 1024 words (0, 1, 127, 511, 512, 513, $4000 and $ffff capped, $8000 copies nothing, $8001, $8200 exactly 1024 with no cap written); 512 written into the caller's contrl[1] BEFORE the copy (a caller whose ptsin is its own contrl copies the 512; v_pline over 513 points draws 512, then the caller's 513 is given back); the copy runs FORWARDS (a caller's ptsin one word below the copy — the review's backwards `copy_words` survived before it); the count given back through LINEA_CONTRL RE-READ after the dispatch (vsf_perimeter's intout laid over LINEA_CONTRL moves it); D0.w = VDI_RESULT (vsm_height), ptsin[1] read from the copy; the pointers' top byte kept, not driven. The `.S` is the entry's own register convention, which no C function has (the timer_tick precedent): it hands D1-A6 back to the `trap #2` caller, D0's high word the dispatched function's (the walk's `move.l a4,d0` at `$fcaa38`; no caller reads it), pinned by `test_the_entry_keeps_every_register_but_d0_s_low_word`; the C twin answers the WORD. Mutation: in vdi_dispatch's sweep (one equivalent: contrl re-read for the count) |
| `0xfca9f6` | vdi_dispatch (`src/vdi/entry.c`; ships as C, its call through `staged_call.h`'s `call_vector_keeping`) | 56 | 64 / 1134 physical, 79 / 1284 three links along, 44 / 590 unknown handle | **1.02** the physical workstation, **1.01** three links along, **0.81** an unknown handle | ✅ verified | the handle and the opcode read BEFORE VDI_RESULT is cleared (contrl[6] and contrl[0] laid over VDI_RESULT), contrl[2]/[4] and VDI_RESULT cleared BEFORE the walk (contrl over a record's WS_HANDLE; VDI_RESULT as a record's handle); the list band 3's chain builds (1,2,4,3,3), each record with its own write mode and clip: the physical record, one and two links along, the duplicate handle (first match wins, three links along), an unknown handle walking the whole list and calling nothing, the handle compared as a whole word ($0101, and a record holding $0101 found for $0101); 1 (v_opnwk) and 100 (v_opnvwk) reached end to end with an unknown handle (the lookup skipped); every range edge (0, 40, 99, 132, −1, −32768, $7fff make the workstation current and call nothing; 39, 104, 131 run into the real C); the copies held to `vdi.DISPATCH_STEPS` — ONE ordered list (CUR_WORK, the 21 copies, MULTIFILL after PATMSK, MONO_STATUS after CUR_FONT) that the model folds, the ROM's own first store to each byte asserted in that order and every byte the ROM stores asserted to be some step's (all 20 adjacent swaps and all 24 dropped steps RED; 4 swaps were fully green before the review), and the C held to the ROM's order by 19 overlaid placements a model-guided search found (every adjacent pair but WS_CLIP's two, which commute; `RUN_SLOW=1` re-runs the 48 s search); MULTIFILL for the user interior alone; MONO_STATUS read back through LINEA_CUR_FONT, with records at $260a/$260e partly over it. `call_vector_keeping` saves D2-D7/A2-A6 round the `jsr` only, so a lookup that calls nothing pays no prologue (the ordinary shape measured 1.09 there). `make_current` keeps one held record base, the ROM's A4, and the block and the ptsin copy walk from a base masked once (the ROM's A5; the per-field form changed target code) — they differ from per-field masking only for a record within a record's size of the bus top, the I/O page. Mutation (strict, the fixed privlib, entry.c + the hoisted accessors): 112 — 103 killed, 5 equivalent, 2 UNPINNED host-only (next_of/handle_of masked before the offset: a link within 64/40 bytes of $1000000), 2 ABNORMAL (the tests fail, then the host follows a stale index) |
| `0xfd1038` | `linea_cpu_blit` (`src/vdi/blit.c`; `blit.S`) | 613 | 962 / 9074, 4997 / 39776, 686 / 5910, 244 / 2790 | **7.55**, **7.35**, **3.74**, **2.87** (T); `.S` **1.00** ×4 | ✅ verified | the threaded engine: all 16 aligners × both directions × widths (shift 0 with odd spans = aligner 8), 16 ops with and without a pattern, the fast copy, direction by a 32-bit address compare, the latch's stale high half; P_ADDR re-tested PER PLANE (a plane stepped to P_ADDR 0 ANDs nothing); MIDDLE_COUNT re-read before every row and per plane on the no-source path; the runaway counts pinned (height 0 → 65536 rows, plane count 0 → 65536 planes, a one-word-source fast copy). `.S` byte-exact but for 57 pinned relocations. Strict mutation: C 101/109 (6 survivors equivalent or host-UB, 2 abnormal = process aborts), `.S` 54/56 |
| `0xfd05fc` | `linea_bitblt` $a007 (same) | (engine battery) | 711 / 6774, 274 / 3002 | **7.55**, **2.73** (T); `.S` **1.00** ×2 | ✅ verified | a6 = the caller's block `adda #76`; the far corners and engine scratch stored back into it |
| `0xfd0346` | `linea_copy_raster` $a00e (same) | 120 | 5891 / 48308, 4620 / 37956, 92 / 1318 | **8.77**, **9.23**, **1.40** (T); `.S` **1.00** ×3 | ✅ verified | MFDB → BITBLT frame (null base = the screen, WIDTH); bit 4 = the PATTERN flag (the map had it as opaque/transparent); transparency via COPY_TRAN; clips only a screen destination; the pen test `bmi` (negatives index MAP_COL backwards); the dest-plane `btst` mod 32; six refusals |
| `0xfcb5aa` | `vro_cpyfm` (109, same) | 5 | 5457 / 48236 | **1.00** (T→ through) | ✅ verified | both rectangles sorted in place (arb_corner); measured as it ships (through the `.S`) |
| `0xfcb5dc` | `vrt_cpyfm` (121, same) | 5 | 5142 / 42774 | **1.00** (T→) | ✅ verified | COPY_TRAN = $ffff |
| `0xfcb614` | `vr_recfl` (114, same) | 28 | 6563 / 60778, 863 / 7040 | **1.00**, **1.04** (T→) | ✅ verified | WS_FILL_COLOR spread into COLBIT; `$a005`; saves D6 unused |
| `0xfcee54` | `$a008 textblt` (`src/vdi/text_raster.c`; `text_raster.S`) | 1675 | 1487 / 15522 two words, 723 / 8676 one word, 5390 / 52130 bold italic, 2726 / 29456 light, 4682 / 45304 outlined turned, 8834 / 85130 scaled, 68 / 892 clipped away | **4.28**, **3.45**, **3.35**, **4.21**, **2.65**, **3.57**, **1.49** (T); `.S` **1.00** ×7 | ✅ verified | all 20 write modes + the stray modes past 19 that land on ops (the ones read from the easter egg `"  Dave StaUgas loves Bea Hablig "`), every effect alone and combined, four row loops, the skew step's two polarities, rotation 90/180/270/other, DDA scaling, each clip edge, 1-4 planes; an ODD op index (the ROM's address error) and an op slot naming an EFFECT fragment HALT on both builds (mode 44 + LIGHTEN spins in the ROM). Strict mutation: C 203/224 (18 equivalent — six thicken-first reasoned, not proved; 3 abnormal = the C's own halts) |
| `0xfd1df6` | CPU TextBlt, vector 9 (same) | (above) | `.S` 1490 / 15572 … 71 / 942 | C unpriced (entered only below `$a008`'s frame); `.S` **1.00** ×7 | ✅ verified | the `.S` held to the ROM for every write mode up to 576 (the computed limit where the op tables leave the transcribed region); `.S` 24/28 strict (4 equivalent, one believed not proved) |
| `0xfcf96a` | `fast_text_try` (same) | 163 | 11359 / 108310 forty chars, 2581 / 22398 six, 10 / 128 refused | **3.10**, **1.95**, **1.25** (T); `.S` **1.00** ×3 | ✅ verified | shared refusal BEFORE its entry ($fcf964), a conservative clip test (a glyph touching the far edge refused), the count a whole word |
| `0xfd1cc4` | CPU fast text, vector 5 (same) | (above) | `.S` 11349 / 108242, 2555 / 22228 | C unpriced; `.S` **1.00** ×2 | ✅ verified | `dbf d3` into the character loop's own `dbf`; the odd/even byte walk |
| `0xfca05e` | `$a006 filled_poly` (`src/vdi/fill.c`; `fill.S`) | 170 | 445 / 4664 pentagram row, 2306 / 25264 comb row | **1.78**, **1.68** (T); `.S` **1.00**, **1.00** | ✅ verified | half-open crossings; on a `divs.w` overflow the crossing takes the sign of the 32-bit PRODUCT (the $8000 low-word case pinned); an odd crossing dropped; the crossing list at $16da unbounded (24 crossings pass $1702); x-clip only |
| `0xfcbf16` | `clip_line` (same) | 14 | 244 / 3554, 56 / 802 | **0.89**, **0.86** (T→) | ✅ verified | Cohen–Sutherland by the lowest outcode bit, first end first; smul_div stored before the edge |
| `0xfcbe8c` | `polyline` (same) | 14 | 10305 / 91874 | **1.00** (T→) | ✅ verified | LSTLIN cleared BEFORE contrl[1] is read, set on the last segment and left at 1 |
| `0xfcc0ea` | `plygn` (same) | 41 | 38114 / 393842 | **1.04** (T→) | ✅ verified | rows maxy..miny+1; a top clip gives YMINCL−1 floored at 1 (rows 0/1 never filled when the clip top is 0); the closing point at ptsin[n]; a perimeter (FILL_PER == 1) PERMANENTLY increments the caller's contrl[1] |
| `0xfcbbc0` | `v_fillarea` (opcode 9, same) | 38 | 29851 / 304280, 68 / 920 | **1.06**, **0.78** (T→) | ✅ verified | plygn |
| `0xfd08f4` | `$a00f contour_fill` (same) | 30 | 5085 / 40174 | **1.04** (T→) | ✅ verified | DRI's seedfill globals at $16da..$1704, a 1920-word queue from $1706 running through the PTSIN copy to $2605; true signed walk compares (a span wider than a word pinned); seed colour vs search colour; SEEDABORT per pass through the ONE register hook. THE ROM CAN HANG: a patterned or same-colour fill never ends by itself — only SEEDABORT stops it |
| `0xfd08e0` | `v_contourfill` (opcode 103, same) | 4 | 19322 / 144280 | **1.03** (T→) | ✅ verified | installs $fc9f9a (never aborts) over any staged SEEDABORT |
| `0xfcfb54` | `fill_span` (same; `.S`) | 8 | 296 / 2524 | **1.68** (T); `.S` **1.00** | ✅ verified | (x1, x2, y) into `$a004`'s patterned entry |
| `0xfcfb66` | `end_pts` (same; `.S`) | 24 | 3939 / 25402, 6 / 98 | **1.89**, **5.14** (T); `.S` **1.00**, **1.00** | ✅ verified | walks the seed pixel's own colour; `adda.w` sign-extends the plane step and A5 drifts as the ROM's `-(a5)` reads leave it (PLANES $4000/$7fff/$8000/$c001/0 pinned in claimed high bands); top by `bmi`; x unchecked |
| `0xfd0dc8` | `crunch_queue` (same) | 8 | 40 / 558 | **0.95** | ✅ verified | reads queue[−3] ($1700) when the queue is empty; long queue indices (the word-wide reach is the I/O page — unpinned) |
| `0xfd0e22` | `get_seed` (same) | 10 | 4130 / 27770, 4234 / 28352 | **1.01**, **1.02** (T→) | ✅ verified | twin = same row, other direction, same left end: drawn and taken; first hole reused; QTMP re-read between the record's three stores |
| `0xfd0fde` | `v_get_pixel` (opcode 105, same) | 13 | 75 / 826 | **1.08** (T→) | ✅ verified | intout[0] stored BEFORE INQ_TAB[4] is read; 1 plane nonzero or 2 planes pen 3 → index 15; REV_MAP_COL index sign-extended |
| `0xfcffb0` | `$a00d draw_sprite` (`src/vdi/mouse.c`; `mouse.S`) | 120 | 1611 / 13686 two groups, 1227 / 10594 clipped left, 406 / 3814 one plane xor | **3.08**, **4.06**, **3.36** (T); `.S` **1.00** ×3 | ✅ verified | each row SAVED before its form words are read (a save area over the form pinned); every alignment, each edge/corner (unsigned clip), 1/2/4/0/3/8 planes, 8 fragments, WIDTH vs BYTES_LIN, the `adda.w` wrap |
| `0xfd0184` | `$a00c undraw_sprite` (same) | 30 | three cases | **8.45**, **3.37**, **7.09** (T); `.S` **1.00** ×2 | ✅ verified | three layouts (3 / 5+ planes restored as 4); round trips. Unstaged: a saved length of 0 (65,536 rows) |
| `0xfd0254` | `$a00a hide_mouse` (same) | 12 | 211 / 2322, 7 / 146 | **7.90**, **1.28** (T); `.S` **1.00** ×2 | ✅ verified | undraws only on reaching 1; CUR_FLAG cleared |
| `0xfd0286` | `show_cursor` (same) | 14 | 1501 / 14450, 6 / 126 | **3.08**, **1.67** (T); `.S` **1.00** ×2 | ✅ verified | `bgt`/`bmi`: depth $8000 draws, below 0 reset undrawn |
| `0xfcb120` | `v_show_c` (122, `$a009`, same) | 12 | 1511 / 14594 forced, 17 / 280 not drawn, 13 / 228 still hidden | **1.01** forced (T→), **1.81** not drawn, **2.05** still hidden (T→G `glue`) | ✅ verified | intin[0]=0 forces depth 1 unless 0. The two light rows are band 4's: the escape's v_dspcur `.S` rows reach v_show_c only as the ROM's own code (escape.S's `jmp` keeps its address), so the C that ships is priced here, net of the glue 0.91 not drawn, 0.90 still hidden (the dearest light path as shipped) |
| `0xfcb148` | `v_hide_c` (123, same) | 2 | 215 / 2386 the arrow removed, 11 / 210 already hidden | **1.06** the arrow removed (T→), **1.78** already hidden (T→G `glue`) | ✅ verified | the light row is band 4's, for the same reason as v_show_c's (the escape's v_rmcur `jmp`s into the ROM's own code): net of the glue 0.69; a deeper hide measures the same |
| `0xfd02ca` | `vsc_form` (111, `$a00b`, same; `.S`) | 13 | 74 / 984 | **2.54** (T); `.S` **1.00** | ✅ verified | 4-bit hot spot; `bmi` colour test (reads below MAP_COL); mask/data read-store order |
| `0xfcfe28` | `mouse_isr` (same) | 26 | three cases | **1.69**, **1.74** (T), **0.98**; `.S` **1.00** ×3 | ✅ verified | user vectors through the ONE D0/D1/A0 hook: dx/dy and `moved` read through the A0 USER_BUT hands back, USER_CUR given USER_MOT's A0; the second clamp; the lock |
| `0xfcff0a` | `default_user_cur` (same) | 5 | 11 / 174 | **1.12** (T); `.S` **1.00** | ✅ verified | queues only while shown; its IPL bracket and the MOUSE_FLAG lock held by the `.S` byte pin only |
| `0xfcff2a` | `vbl_draw_cursor` (same) | 10 | 1700 / 16532, 6 / 114 | **3.76**, **1.65** (T); `.S` **1.00** ×2 | ✅ verified | lock, bit taken, arrow moved |
| `0xfca7f8` | `mouse_init` (same) | 1 | 20191 / 295942 | **1.00** (T→) | ✅ verified | the real XBIOS Initmous trap on target; default user vectors = its own `rts` $fca870; vblqueue[0] |
| `0xfca872` | `mouse_off` (same) | 1 | 2903 / 42686 | **1.00** | ✅ verified | |
| `0xfca7ca` | `poll_key` (same) | 7 | 106 / 1634, 47 / 742 | **1.06**, **1.09** | ✅ verified | scancode byte over the ASCII word |
| `0xfca7c0` | `poll_choice` (same; `.S`) | 3 | 3 / 76 | **1.78** (T); `.S` **1.00** | ✅ verified | never writes D0 |
| `0xfca88a` | `poll_locator` (same; `.S`) | 13 | 57 / 882, 14 / 172 | **1.10**, **1.67** (T); `.S` **1.00** ×2 | ✅ verified | button beats key beats motion; D1 (CUR_MS_STAT) held across `trap #13` |
| `0xfcb002` | `vdi_locator` (28, same) | 13 | 1851 / 18866 request, 87 / 1322 sample | **1.03**, **1.01** (T→) | ✅ verified | writes intin[0]=1 into the CALLER's array; request forces the hide count to 1 and draws without removing; the request spin through the kit's wait-site door (loop-back cases: 2 and 5 passes, motion then a key) |
| `0xfcb1a0` | `vdi_choice` (30, same) | 7 | 16 / 270 | **1.49** (accepted: its own call through the glue) | ✅ verified | D0 = the dispatcher's MONO_STATUS (0/8): REQUEST MODE HANGS FOR EVER in the ROM (poll_choice never writes D0) — the spin pinned to the door's cap host-side, the hang oracle-only |
| `0xfcb22a` | `vdi_string` (31, same) | 13 | 385 / 5730, 303 / 4520 | **0.95**, **0.97** | ✅ verified | RETURN stored not counted; a negative count reads whole scancode words (RETURN never ends it), −32768 reads nothing; late keys through the wait-site door |
| `0xfc9ffc` | `vec_len` (`src/vdi/helpers.c`) | 18 | 243 / 2344 bisection, 64 / 636 exact square | **0.94**, **1.02** | ✅ verified | isqrt(dx²+dy²) by bisection: both halves of the log search, sums ≥2^30 (the $10000→$ffff fix), negatives; clobbers D3/D4 (harmless in every caller) |
| `0xfca164` | `sort_words` (same file; `helpers.S`) | 18 | 195 / 1858 eight reversed, 13 / 138 two in order | **1.54**, **2.33** (T); `.S` **1.00**, **1.00** | ✅ verified | register D0.w/A0; empty, one, equal (kept), reversed, signed extremes, count as a word; the `.S` clobbers D2 |
| `0xfca186` | `smul_div` (same; `.S`) | 22 | 19 / 380 rounded up, 22 / 390 neg / neg | **1.06**, **1.14** (T); `.S` **1.00**, **1.00** | ✅ verified | round(a*b/c): the remainder read through `neg.l` of the whole register (|r|−1 when negative over a nonzero quotient), a divisor of −32768 rounds any remainder, `divs` overflow leaves the product; c=0 REFUSED by name on the host (vector 5 on the 68000); the `.S` clobbers D2 |
| `0xfcab68` | `isin` (same) | 30 | 53 / 1236 interpolated, 40 / 916 whole degree | **0.71**, **0.70** | ✅ verified | the five arms of $fd3900, the table ends, interpolation, the turn loop; negative angles index BELOW the sine table |
| `0xfcac4c` | `icos` (same) | 11 | 61 / 1360 | **0.71** | ✅ verified | isin(a+900) with the word wrap past 32767 |
| `0xfcc092` | `clip_code` (same) | 15 | 20 / 292 corner, 18 / 264 inside | **0.60**, **0.66** | ✅ verified | every edge inclusive, the four corners, signed |
| `0xfcc6b4` | `clc_nsteps` (same) | 14 | 16 / 262 minimum, 15 / 256 within | **0.68**, **0.81** | ✅ verified | max radius / 4 clamped 32..128, signed shift |
| `0xfcced6` | `quad_xform` (same) | 16 | 24 / 288 | **0.90** | ✅ verified | written from the asm (the one hard decompile failure); quadrants 1..4 and the ones storing nothing |
| `0xfcedd0` | `clc_dda` (same; `.S`) | 22 | 12 / 276 down, 13 / 278 up, 11 / 132 doubled | **1.05**, **1.04**, **1.15** (T); `.S` **1.00** ×3 | ✅ verified | (actual, requested); the doubling marker; equal sizes answer 0 (`divu` overflow) and an actual ≤ 0 — both ROM-UNREACHABLE (the only caller $fce076 skips equal sizes), pinned anyway; a requested ≤ 0 is reachable (ptsin[1]) |
| `0xfcee02` | `act_siz` (same; `.S`) | 35 | 79 / 638 down, 81 / 670 up, 12 / 180 doubled, 20 / 250 one line | **1.21**, **1.19**, **0.73**, **1.02** (T); `.S` **1.00** ×4 | ✅ verified | `btst #0,$29df` (bit 0 of the LOW byte); size −32768 = 32768 steps |
| `0xfce0ee` | `copy_name` (same) | 2 | 141 / 1322 | **0.71** | ✅ verified | exactly 32 bytes, forward (an overlap smear pins it) |
| `0xfcfaac` | `font_byteswap` (same) | 9 | 71 / 928 sixteen words, 11 / 208 one word | **1.01**, **1.04** | ✅ verified | the product's low-word truncation; a zero count = 65536 words (a 128 KB form claimed in `staging.HIGH_BANDS` at $90000, held dead) |
| `0xfcd056` | `s_fa_attr` (same) | 3 | 20 / 420 | **0.82** | ✅ verified | every store, on CUR_WORK (a virtual one; the physical untouched) |
| `0xfcd0c2` | `r_fa_attr` (same) | 2 | 12 / 256 | **0.63** | ✅ verified | the round trip via `case.continued` |
| `0xfcfedc` | `clamp_mouse` (`mouse.S`; C in `helpers.c`) | 20 | 11 / 136, 10 / 136 | **2.27**, **2.29** (T); `.S` **1.00**, **1.00** | ✅ verified | moved into `mouse.S` (the ISR reaches it by `bsr.s`); a negative DEV_TAB bound (x=0) pinned on the `.S` too |
| `0xfca648` | `get_kbshift` (same; `.S`) | 11 | 4 / 80 | **2.10** (T); `.S` **1.00** | ✅ verified | its `rts` is vdi_nop's ($fca652) |
| `0xfcfa9c` | `gemdos_call` (same; `.S`) | 6 | `.S` 20 / 410 | C unpriced — its TARGET branch is UNEXERCISED (the ROM build links the `.S`); `.S` **1.00** | ✅ verified | Tier 1 through the REAL `trap #1` into the ROM's GEMDOS vs the reconstructed dispatcher + memory manager (Malloc, Mfree, a refused Mfree), three documented WINDOWS (p_run's register save, GEMDOS's stack, the termination record) of which only the bytes the ROM writes are dropped (`case.run(dropped_windows=)`, band 3 — the stack drop had covered 124–200 bytes the ROM never writes); the `.S` over a staged recording trap handler whose ledger now APPENDS (8 entries; +4 insns / +48 cycles a trap on both columns); returns through whatever RETSAV holds (not exercised with a changed value). Band 3's workstation rows execute its generated glue thunk (136 cycles) |
| `0xfd2d32` | `vr_trnfm` (opcode 110, same; `.S`) | 74 | 134 / 1522, 122 / 1420 copy; 537 / 4910, 527 / 4828 in place; 35 / 580 one word | **0.94**, **0.94**, **1.32**, **1.35**, **1.04** (T); `.S` **1.00** ×5 | ✅ verified | copy $fd2db4 and in-place $fd2d80; 1-4 planes, odd width, both directions, one MFDB as both; contrl, both MFDBs and both forms tagged (the 24-bit bus), and two forms differing only in the top byte COPIED over each other (`cmpa.l` of the whole longwords), the tagged host core returning in a child; the `.S` clobbers D7 outside its movem |
| `0xfca1b8` | `concat` (`src/vdi/raster.c`; `raster.S`) | 36 | 15 / 216 | **1.70** (T); `.S` **1.00** | ✅ verified | offset = y·BYTES_LIN + ((x&~15) asr SHIFT[PLANES]); the shift table starts at the low byte of its own `rts` (only 1/2/4/8 planes right) and its count is taken mod 64, ≥16 leaving x's sign (13/18 planes pinned); D0.w = x&15, D2's high word clobbered |
| `0xfcface` | `$a001 put_pixel` (same) | 37 | 47 / 552 | **1.39** (T); `.S` **1.00** | ✅ verified | colours 0..15, 1/2/4 planes and a 13-plane large-x case; unclipped; also through the Line-A exception |
| `0xfcfb16` | `$a002 get_pixel` (same) | 15 | 55 / 526 | **1.28** (T); `.S` **1.00** | ✅ verified | D0 whole, last plane first, a WORD accumulator (17 planes pinned). Unstaged: PLANES 0's 65536-pass runaway |
| `0xfca57e` | `$a004 hline` (same) | 228 | 99 / 870 one pixel, 330 / 3204 many groups, 108 / 938 two groups xor | **2.60**, **1.42**, **2.53** (T); `.S` **1.00** ×3 | ✅ verified | 4 write modes × colours × 6 span shapes; real patterns incl. multi-plane; row 0 by BYTES_LIN with WIDTH ± 8; the style sits on the screen's 16-pixel grid |
| `0xfca58a` | `$a004` patterned entry (same) | 72 | 124 / 1116 | **2.18** (T); `.S` **1.00** | ✅ verified | contour fill's D4/D5/D6 mid-function entry |
| `0xfca5a2` | `$a004` span entry (same) | 96 | 89 / 760 | **2.83** (T); `.S` **1.00** | ✅ verified | A0 = the pattern word, D0 = the stride |
| `0xfd1ae0` | CPU hline body, vector 8 (same) | 96 | `.S` 77 / 710, 291 / 2826 | C unpriced (8 C arguments; priced inside the `$a004` rows); `.S` **1.00**, **1.00** | ✅ verified | entered directly; stride-32 user-pattern cases |
| `0xfcfc56` | `$a005 filled_rect` (same) | 203 | 126 / 1120, 1536 / 13940, 702 / 5830, 23 / 262 | **2.30**, **2.17**, **2.18**, **2.28** (T); `.S` **1.00** ×4 | ✅ verified | clip cutting/touching/missing every side, the partially clipped corners STORED even on a miss; the pattern row wraps by compare past PATMSK·2; rows placed with BYTES_LIN, stepped with WIDTH |
| `0xfd1b16` | CPU rect-fill body, vector 6 (same) | 64 | `.S` 107 / 980, 4900 / 46450 | C unpriced (7 C arguments); `.S` **1.00**, **1.00** | ✅ verified | entered directly; hatch and MULTIFILL cases |
| `0xfca1ea` | `$a003 line` (same) | 525 | 129 / 1214 … 841 / 7334 | **1.85**, **2.97**, **2.39**, **3.25**, **1.77**, **2.46**, **1.47** (T); `.S` **1.00** ×7 | ✅ verified | three arms: horizontal (XOR without LSTLIN writes the shortened X2 back), vertical, and the DIAGONAL Bresenham that runs per-plane code BUILT ON THE STACK by $fca3f4; 8 octants, the 45° and error-0 slopes, LSTLIN, LN_MASK rotation; PLANES 8 draws, 9 returns untouched |
| `0xfd19dc` | CPU vline, vector 7 (same) | 40 | 584 / 5756, 83 / 830 | **3.18**, **1.37** (T); `.S` **1.00**, **1.00** | ✅ verified | entered directly, all modes, up and down (its only callee is $fca3f4 — the map's textblt-helper claim was wrong) |
| `0xfca3f4` | `line_plane_words` (same) | 16 | 23 / 252 | **2.70** (T); `.S` **1.00** | ✅ verified | the per-plane and/or opcodes a line body runs + `jmp (a3)` |
| `0xfcac76` | `vsl_type` (`src/vdi/attributes.c`) | 14 | 22 / 306 in range, 21 / 298 out of range | **0.68** in range, **0.73** out of range | ✅ verified | style 1..7 stored 0-based, else 0; contrl[4] first |
| `0xfcacc0` | `vsl_width` (same file) | 23 | 27 / 536 capped, 26 / 508 below 1 | **0.62** capped, **0.49** below 1 | ✅ verified | clamp 1..SIZ_TAB[6] with the ROM's truncating `divs.w #2` round-down to odd (a staged odd cap and caps below 1); point order pinned by ptsout laid over contrl[2] and WS_LINE_WIDTH |
| `0xfcad20` | `vsl_ends` (same file) | 11 | 28 / 408, 28 / 398 | **0.72** in range, **0.75** both out of range | ✅ verified | both ends 0..2 else 0 |
| `0xfcad7c` | `vsl_color` (same file) | 21 | 22 / 332, 21 / 324 | **0.78** in range, **0.72** out of range | ✅ verified | the bound is DEV_TAB[13] itself (`cmp.w; bge`): a colour count of $8000 makes every index 1; MAP_COL pen stored |
| `0xfcb4a2` | `vsl_udsty` (same file) | 6 | 7 / 140 | **0.92** | ✅ verified | stored raw; no answer, no count, LN_MASK untouched |
| `0xfcadcc` | `vsm_height` (same file) | 31 | 32 / 868 rounded up, 33 / 882 capped | **0.84** rounded up, **0.82** capped | ✅ verified | clamp to SIZ_TAB, scale by `divs.w`, sets VDI_RESULT; point order pinned (ptsout over contrl[2], MARK_HEIGHT, MARK_SCALE). Unpinned: a zero smallest height (the divide) |
| `0xfcae58` | `vsm_type` (same file) | 13 | 24 / 314, 25 / 322 | **0.66** in range, **0.67** out of range | ✅ verified | 1..6 else the default; contrl[4] last |
| `0xfcaea8` | `vsm_color` (same file) | 16 | 24 / 340, 25 / 348 | **0.76** in range, **0.70** out of range | ✅ verified | as vsl_color, contrl[4] last |
| `0xfcaefe` | `vsf_interior` (same file) | 16 | 54 / 750, 42 / 632 | **0.80** hatch, upper table, **0.69** out of range | ✅ verified | 0..4 else hollow; then st_fl_ptr |
| `0xfcaf4a` | `vsf_style` (same file) | 24 | 58 / 808, 56 / 792 | **0.81** pattern, upper table, **0.83** out of range | ✅ verified | bound 24 under pattern, 12 otherwise; a pattern style carried into hatch points PATPTR at MAP_COL (a chained case) |
| `0xfcafb2` | `vsf_color` (same file) | 16 | 22 / 332, 21 / 324 | **0.78** in range, **0.72** out of range | ✅ verified | as vsl_color |
| `0xfcd6fa` | `vsf_udpat` (same file) | 10 | 280 / 2316, 84 / 832, 18 / 332 | **0.95** every plane, **0.85** one plane, **0.54** refused | ✅ verified | 16 or 16×planes words, else refused silently (nothing stored, not even MULTIFILL). Unpinned: more than 4 planes |
| `0xfcc9a6` | `st_fl_ptr` (same file) | 12 | 34 / 472, 24 / 362 | **0.84** pattern, upper table, **0.81** user | ✅ verified | the five interiors via $fd397c, both thresholds of both tables. An interior >4 stores an unloaded A5 — callers clamp, the C halts, an oracle-only case pins it |
| `0xfce3b2` | `vst_effects` (same file) | 15 | 13 / 224 | **0.91** | ✅ verified | masked by INQ_TAB[2] |
| `0xfce3e6` | `vst_alignment` (same file) | 16 | 28 / 424, 30 / 428 | **0.74** in range, **0.75** out of range | ✅ verified | h 0..2, v 0..5; intin[1] read after intout[0] |
| `0xfce442` | `vst_rotation` (same file) | 25 | 16 / 428, 16 / 428 | **0.97** rounded up, **0.97** negative | ✅ verified | `add.w #450` wraps (32318 → -32400), `divs.w`/`muls.w #900` |
| `0xfce560` | `vst_color` (same file) | 16 | 22 / 332, 21 / 324 | **0.79** in range, **0.73** out of range | ✅ verified | as vsl_color |
| `0xfcb32e` | `vswr_mode` (same file) | 13 | 28 / 346, 28 / 340 | **0.61** in range, **0.64** out of range | ✅ verified | 1..4 stored 0-based; the dispatcher's Line-A copy NOT updated (no setter writes one) |
| `0xfcb388` | `vsin_mode` (same file) | 45 | 25 / 366, 24 / 350 | **0.77** string, sample, **0.57** no such device | ✅ verified | mode echoed raw, stored minus one; device read after the echo (overlap (1,3)) |
| `0xfcb3f6` | `vqin_mode` (same file) | 12 | 22 / 330 | **0.73** | ✅ verified | answers the stored mode (mode−1): sample reports 1 |
| `0xfcb4ba` | `vs_clip` (same file) | 39 | 69 / 914, 16 / 350 | **0.83** reversed, cut, **0.70** off | ✅ verified | sorts ptsin in place (arb_corner), then walks PTSIN from ONE read of the pointer (`movea.l $29a6,a5` / `(a5)+`: respelt in band 2, which also closed a latent divergence for a ptsin laid over `$29a6`); flag stored raw; one-sided bounds |
| `0xfcb55e` | `arb_corner` (same file) | 28 | 26 / 364 | **0.81** | ✅ verified | x always ascending, y by order; sorts in place |
| `0xfca6a4` | `vex_timv` (same file) | 6 | 40 / 770 | **1.09** (pinned) | ✅ verified | exchange under `ori #$700`, Tickcal via trap #13; contrl[4] never set. Same-cost SR mutants unpinned (the SR surface is a kit item) |
| `0xfcff68` | `vex_butv` (same file) | 4 | 5 / 140 | **1.08** | ✅ verified | exchange order pinned (contrl[9..10] over USER_BUT); runs unmasked |
| `0xfcff80` | `vex_motv` (same file) | 4 | 5 / 140 | **1.08** | ✅ verified | same |
| `0xfcff98` | `vex_curv` (same file) | 4 | 5 / 140 | **1.08** | ✅ verified | same |
| `0xfca652` | `vdi_nop` (opcodes 4/10/27/34, `src/vdi/inquire.c`) | 4 | 2 / 56 | **1.00** | ✅ verified | nothing written, not even a count |
| `0xfcb198` | `vdi_valuator` (opcode 29, same file) | 1 | 4 / 84 | **0.36** | ✅ verified | link/unlk/rts |
| `0xfcbd7e` | `vql_attributes` (same file) | 28 | 25 / 394 | **0.94** | ✅ verified | mode = the Line-A copy + 1; REV_MAP_COL; no VDI_RESULT; ptsout pointer read after the intout stores |
| `0xfcbdda` | `vqm_attributes` (same file) | 25 | 24 / 406 | **0.93** | ✅ verified | marker type 0-based; sets VDI_RESULT; contrl[4] before [2]; ptsout pointer read after intout |
| `0xfcbe3a` | `vqf_attributes` (same file) | 24 | 23 / 362 | **0.89** | ✅ verified | no points |
| `0xfcb8d0` | `vq_extnd` (same file, + `$fc4e06`) | 23 | 258 / 2390, 251 / 2420 | **0.81** plain, **0.81** extended | ✅ verified | intin[0] read twice (the second decides the speed); the intout pointer reloaded for it; VDI_RESULT=1 |
| `0xfced9a` | `vst_unload_fonts` (same file) | 2 | 12 / 256 | **0.72** | ✅ verified | leaves the ring's loaded slot and WS_CUR_FONT naming the unloaded font |
| `0xfcb156` | `vq_mouse` (same file) | 5 | 15 / 292 | **0.78** | ✅ verified | |
| `0xfcb30a` | `vq_key_s` (same file) | 8 | 13 / 220 | **1.52** (accepted: (A)+(D) — its own call through the glue, measured as it ships) | ✅ verified | count before answer |
| `0xfce5b0` | `vqt_attributes` (same file) | 26 | 32 / 538 | **1.02** | ✅ verified | write mode 0-based FROM THE RECORD; FONT_TOP read after ptsout[0]; ptsout pointer after intout |
| `0xfce8ca` | `vqt_name` (same file) | 17 | 184 / 1654, 243 / 2252, 268 / 2452 | **0.91** face 1, **0.86** last loaded face, **0.85** past the ring | ✅ verified | 34 words written, 33 counted; a 32-char name runs into FONT_FIRST_ADE; ring walk stops at an empty slot; the 6x6 fallback |
| `0xfce95a` | `vqt_fontinfo` (same file) | 12 | 32 / 552, 30 / 524 | **0.97** bold italic, **0.98** plain | ✅ verified | LINEA_STYLE tested twice at the ROM's points; ptsout pointer after intout |
| `0xfd2dd2` | `vs_color` (`src/vdi/palette.c` + `palette.S`) | 92 | 56 / 978 low res, 49 / 540 mono white, 8 / 128 refused | C **1.68**, **1.84**, **2.77** (T); `.S` **1.00**, **1.00**, **1.00** | ✅ verified | byte bound; the palette address folded to 24 bits (30 low-res indexes wrap into $40..$5e); per-mille → 3 bits; the mono arm; `.S` byte-exact. Unpinned: a row-below-0 store (bus error on iron, dropped by the oracle) |
| `0xfd2e84` | `vq_color` (same files) | 114 | 44 / 516 realized, 23 / 338 requested, 28 / 330 mono, 16 / 236 refused | C **1.81**, **2.59**, **1.56**, **1.53** (T); `.S` **1.00** ×4 | ✅ verified | requested row interleaved read/write; realized from folded low RAM; a row below 0 read from the I/O page (declared); STE fourth bit ignored |
| `0xfc4b7c` | `clear_span` (the BIOS's `bzero`, `src/vdi/screen.c`; `screen.S`) | 22 | 1276 / 74598 the screen, 545 / 5012 odd, a block and a tail | **3.87**, **2.06** (T); `.S` **1.00** ×2 | ✅ verified | moved out of `pexec_load.c` and transcribed: the C twin is 3.87× because the ROM clears with `movem.l` of eight zero registers, which no C reaches. Ten spans across the three steps (odd byte, 256-byte blocks stored DOWNWARDS, byte tail), the same ten through the `.S`; `to` compared for EQUALITY; the counting is 32 bits and the stores 24 (`_v_bas_ad` $ff0f8000 clears $0f8000). `.S` byte-exact, $6c bytes, nothing excused. GEMDOS's loader and v_clrwk/init/restore reach it through the shipped glue (T→). Strict mutation: all 6 of screen.c's survivors are here — span splits that clear the same bytes, and `<` for `!=` (the runaway: reachable, not staged); 1 ABNORMAL (the host bus assert) |
| `0xfca654` | `v_clrwk` (opcode 3, same) | 4 | 1282 / 74726 | **1.00** (T→) | ✅ verified | `clear_span(_v_bas_ad, _v_bas_ad + 32000)`, a LONG sum; even, odd +1 and +$81 bases; the top byte dropped by the bus. Hand asm in the ROM (no `link`), not Alcyon |
| `0xfca670` | `init_timer_mouse` (v_opnwk's, same) | 6 | 21558 / 371792 | **1.00** (T→) | ✅ verified | USER_TIM = $fca652; etv_timer exchanged under the IPL mask into NEXT_TIM; mouse_init; the cursor locked (depth + 1, the drawn cell inverted or not, ×3); the clear. The IPL mask pinned on the SHIPPED ELF (`ori #$700` round the `trap #13`; none in restore). Re-opening chains the tick to ITSELF (pinned) |
| `0xfca6d4` | `setres` (same) | 26 | 75 / 1300 low kept, 78 / 1324 medium kept, 69 / 1244 mono | **1.05** low kept, **1.05** medium kept, **1.04** mono | ✅ verified | mono answers 3 with the MEDIUM palette whatever is asked; intin[0] 1 keeps, 3 asks medium, EVERY other word asks LOW (GEM's 4 included); word compares ($0101/$0103 are neither). The two SWITCHING arms (9 cases) halt inside Setscreen (console_reinit) and now pin the MODE — named in the halt, and the ROM's pushed word at `$fc0ae0` — and that NOTHING is stored before the halt (a shared-memory child image) |
| `0xfca78a` | `timer_tick` (etv_timer, same; `screen.S`) | 16 (6 C, 10 `.S`) | 12 / 588 | **0.98**; `.S` **1.00** | ✅ verified | USER_TIM through the one hook, then NEXT_TIM with the tick word; NEXT_TIM read AFTER USER_TIM; ticks 20/0/$8000/$ffff. SHIPS AS THE ROM's OWN 24 BYTES — the entry a vector holds (etv_timer), which the word-convention C core cannot be: transcribed.h row = the vector set D2-D7/A2-A5, MEASURED with a chained NEXT_TIM that clobbers it; the USER_TIM stubs clobber D0-D7/A0-A5, so the ROM's `movem` bracket is really pinned. Pinned region exactly $fca78a..restore. `.S` mutation 8/8 by the byte pin |
| `0xfca7a2` | `restore_timer_mouse` (v_clswk's, same) | 4 | 4360 / 119416 | **1.01** (T→) | ✅ verified | etv_timer given back UNMASKED (NEXT_TIM with bit 31 set = Setexc report-only: the tick stays installed); mouse_off; clear; the cursor forced on AFTER the clear (drawn over the cleared screen). The real routine is 30 bytes; cfg.txt's [fc45be..fca7c0) was only its `bra` tail |
| `0xfcb9e0` | `v_pline` (opcode 6, `src/vdi/lines.c`) | 46 | 13886 / 139072, 80029 / 821342, 54 / 744 | **1.05** one pixel, dash-dot, both arrowheads, **1.06** width 9, round ends, **0.91** one pixel, no points (T→) | ✅ verified | LN_MASK from VDI_LINE_STYLES below 6 (a negative index reads below the table), else UD_LS; width exactly 1 = polyline + arrowheads over it, else wline; the attribution pass off only where it reaches arrow |
| `0xfcba7a` | `v_pmarker` (opcode 7, same) | 29 | 3479 / 42686, 337 / 4264 | **1.00** five crosses, **1.03** one dot (T→) | ✅ verified | five line fields borrowed and restored (attributed by the poisoned pass); LINEA_CLIP = 1 left set; the caller's contrl[1] left at the last polyline's count (the cross: 2); a mark read after the marks before it are drawn (overlap) |
| `0xfcca86` | `cir_dda` (same) | 75 | 885 / 16876, 99 / 1964 | **0.83** the widest line, **0.89** a one-pixel line | ✅ verified | product low words; rows averaged in place; every odd width 1..39 in three aspects; a width of 79 writes Q[40] = STR_MODE. Unpinned: a zero pixel height or an aspect wider than tall (a zero divide — the host refuses by name) |
| `0xfccba0` | `wline` (same) | 64 | 115588 / 1197206, 28077 / 294148 | **1.06** zigzag, width 9, **1.07** one segment, width 3 (T→) | ✅ verified | the caller's contrl[1] left at 5; the circle keyed by width only (one built for another aspect kept); a begin/end word of 1 (arrow) gets the round disc too (`tst.w $2628`); points re-read after each segment (overlap) |
| `0xfccd92` | `perp_off` (same) | 157 | 452 / 5808, 129 / 1798 | **0.69** width 15, steep, **0.76** the widest, shallow | ✅ verified | word cross product with a true signed `blt` abs; ties to the diagonal; 37 directions incl. (-32768, 0) (kills the quadrant-2/3-at-y=0 mutant). Unpinned: a first product of 32767 reads two uninitialised frame locals (stack garbage in the ROM; the C starts them at (0, 0)) |
| `0xfccf4e` | `do_circ` (same) | 26 | 2772 / 27668, 547 / 5890 | **1.04** width 15, replace, **1.07** width 3, xor (T→) | ✅ verified | clip_line whatever CLIP says; every mode at four widths; clipped at every edge; NUM_QC_LINES 0 and negative |
| `0xfcd0fa` | `arrow` (same) | 67 | 5775 / 66750 width 1, 5777 / 66830 width 3 | **1.10** long segment, width 1, both ends (T→G `glue`), **1.10** both ends, width 3 (T→) | ✅ verified | the original first point put back before the end arrowhead's contrl[1] read (overlap). The WORST realistic row is width 1 (v_pline's one-pixel path): 1.1006 as shipped, NET OF THE GLUE 0.99 (7136 cycles inside the thunks); the attribution pass off (it re-reads LINEA_PTSIN after do_arrow puts it back) |
| `0xfcd196` | `do_arrow` (same) | 38 | 1976 / 23542, 2424 / 28586, 248 / 3034 | **1.14** long segment, width 1, **1.13** one-pixel line, walked past short segments (T→G `glue`), **1.09** all too short (T→) | ✅ verified | contrl[1] = 3 stored before the point is read (overlap); walked points moved onto the base and the count restored. NET OF THE GLUE 1.01 and 1.01 (2920 / 3392 cycles inside smul_div's thunk and, within plygn, `$a006`'s) — the hand "(D)" acceptance the band first proposed is gone. Unpinned: contrl[1] < 2 compares a length never computed |
| `0xfcde9c` | `text_init` (`src/vdi/text.c`) | 7 | 117 / 1674, 134 / 1890 | **0.87** the snapshot's ring, **0.85** a chain of three faces | ✅ verified | slots 0/2/3 fixed then slot 1 walked; LAST default wins; faces = id changes + 1; SIZ_TAB char sizes UNSIGNED over face 1; Intel forms swapped WITHOUT the flag (a second call swaps back) |
| `0xfcdfd0` | `vst_height` (opcode 12, same) | 24 | 122 / 1456 exact, 816 / 8238 scaled, 71854 / 577012 through the bus | **1.00** an exact size, **1.07** scaled up, **1.00** chain on from 0 through the 24-bit bus (T→) | ✅ verified | tallest fit, UNSIGNED, walks on through later slots; NDC; a face not in the ring (after vst_unload_fonts) scales the vector table at address 0, and an id equal to the word at 0 follows vector 21 through the 24-bit bus (the unmasked target path, priced). ROM finding: that chain-on-from-0 case makes the ROM ITSELF do two odd word/long accesses (the first at `$20027`, PC `$fce040`) — a real 68000 takes an address error there, so the verified case is a faithful differential of a run no machine completes; the build reproduces both accesses, and Tier 3's odd-access refusal excuses exactly that (the build makes the same odd accesses as the original: equal count, equal addresses) |
| `0xfce116` | `make_header` (same) | 22 | 614 / 6150 fraction, 304 / 3574 doubled | **1.09** scaled up by a fraction, **1.07** doubled (T→) | ✅ verified | point ALWAYS doubled; top/ascent/half 2n+1 under the marker; FONT_NEXT not copied; GCC's act_siz calls go through an address loaded as an IMMEDIATE (`move.l #act_siz,d2`), which the call graph now resolves, so the row is priced through the `.S` |
| `0xfce26c` | `vst_point` (opcode 107, same) | 19 | 141 / 1608 exact, 483 / 5580 doubled | **0.91** an exact size, **1.01** doubled (T→) | ✅ verified | SIGNED compares; the doubled candidate; the snapshot's own 6x6 doubled to 16 pt beats the 10 pt |
| `0xfce47c` | `vst_font` (opcode 21, same) | 11 | 778 / 8670 height, 234 / 2902 point | **1.05** by height, scaled, **0.90** by point (T→) | ✅ verified | fallback 6x6; re-asks the old size over its own frame (host slot VDI_VST_FONT_CALL); counts before the answer (overlap) |
| `0xfce62a` | `vqt_extent` (opcode 116, same) | 52 | 263 / 2568 twelve, 572 / 4830 effects, 65 / 918 one | **0.80** twelve characters, 8x8, **0.91** every effect, scaled, **0.95** one character (T→) | ✅ verified | sums IN MEMORY at $1706 and re-reads $1706/$1708 per corner; other rotations answer no corners (contrl[2] still 4); the 270° box is wrong (ROM bug, pinned) |
| `0xfce7f0` | `vqt_width` (opcode 117, same) | 31 | 41 / 578, 81 / 996, 22 / 408, 53 / 692 | **0.94** 8x8, **1.15** proportional, offsets, scaled (T→G `glue`), **0.96** outside the font, **0.95** ptsout over the font's HOR_TABLE (T→) | ✅ verified | offsets cleared before intin; unsigned bounds; the HOR index wraps at $4000 where the offset index does not; HOR_TABLE RE-READ after the left offset's store, pinned in BOTH tiers (target TBAA had fused it). The proportional row is 1.15 as shipped, NET OF THE GLUE 1.08: the rest is the faithful second read and GCC's spills round the conditional act_siz under `-fno-strict-aliasing` |
| `0xfced06` | `vst_load_fonts` (opcode 119, same) | 7 | 6468 / 77936, 15 / 326 | **1.00** three GDOS fonts, two forms turned, **0.98** already loaded | ✅ verified | once only; turns and FLAGS each Intel form; faces = id changes; NO GEMDOS call (the map was wrong); reads contrl[10..11], past the 11 words the others use |
| `0xfcc914` | `clc_pts` (the arcs' point, `src/vdi/arcs.c`) | 126 | 191 / 3806 | **0.87** an interpolated angle (T→) | ✅ verified | every octant, 0 / 3599 / 3600 / 3601 / 5000 / two turns and negative angles (isin reads below its table); radii 0, negative and 30000 (the word wraps); indices 0..258 and a NEGATIVE one (sign-extended, then doubled); PTSIN read once, YRAD/YC RE-READ after the x store (ptsin laid over YRAD). Entered by `jsr` as vdi_gdp's arms leave the machine (band 4 reconstructs the arms) |
| `0xfcc79e` | `clc_arc` (same) | 35 | 93297 / 937800 circle, 13 / 238 clipped away | **1.01** circle, radius 60, filled and outlined, **0.69** trivially clipped away (T→) | ✅ verified | the circle and ellipse arms' scratch, 32 and 128 steps; the trivial reject as WORD sums when CLIP is on (each side one past and exactly at the edge, the sums wrapped both ways), none with CLIP off; the LAST point at END_ANG, not START + DEL; contrl[1] = N + 1, a pie N + 1 more and its centre, contrl[5] RE-READ at every test (a pie whose centre lands on contrl[5] turns into an arc). The curve sits in a `noinline` `draw_arc` (the clipped-away row was 1.27 with the 8-register `movem` on the reject path). Dead store: i = n_steps after the loop |
| `0xfcc62e` | `gdp_arc` (GDP 2 / 3, same) | 35 | 91209 / 922848 pie, 16933 / 239968 dash-dot | **1.01** pie, three quadrants, outlined, **0.95** arc, dash-dot (T→) | ✅ verified | nine sweeps × {arc, pie} (past 0, a whole turn, none, past a turn, negative begin, backwards, reflex): angles NEVER normalised, only DEL lifted by 3600 below 0; END read after BEG is stored (intin over GDP_ANGLE); radius ptsin[6], the y radius by the aspect (three aspects), radii 0 / −30 / 1 / 700; seven line styles, widths 3 and 9 through wline, unclipped |
| `0xfcc714` | `gdp_ell` (GDP 6 / 7, same) | 26 | 107051 / 1078548, 14192 / 215798, 52 / 876 | **1.02** elliptical pie, tall, wraps past 0, **0.95** elliptical arc, one quadrant, **0.77** clipped away (T→) | ✅ verified | the same sweeps × {6, 7}; below XFM mode 2 (signed) the y radius is DEV_TAB[1] − yrad (NDC, the GEM behaviour; −1 / 0 / 1 / 2 / 3); arrowheads through v_pline. The ellipse arm stages END_ANG = 0 where the circle arm stages 3600 — the same point. Band 4 re-registered the worst row on the TALL ellipse (review A measured 90x50 at 1.0096 against tall's 1.0189; the wrapping pie stays the row) |
| `0xfcc284` | `gdp_rbox` (GDP 8 / 9, same) | 91 | 7589 / 83262, 96232 / 1075730, 27928 / 278492, 1331 / 17904 | **1.03** outlined, one pixel, **1.06** outlined, width 3, **1.04** filled, outlined, **1.03** a point, filled (T→) | ✅ verified | four corner orders; narrow, short, line and point boxes, odd half-sizes; XRAD = DEV_TAB[0] >> 6 held to the half-width, the centre RE-READ at every store (y before x on backward corners, x before y on forward ones); seven styles and a negative index, widths 3 / 9 and −3 / −1 (vsl_width's stored negatives, SIZ_TAB[6] lowered: kills `== 1` → `<= 1`), modes × colours × patterns, clipped, medium / high; PTSIN RE-READ after the sort (ptsin at `$29a4`); seven WRAPPED geometries that return, filled and outlined w3 and poisoned, each behind a 10 s host-return bound. arb_corner sorts through the CALLER's A5 — at both of vdi_gdp's `jsr`s A5 = PTSIN (review A read it), so the C's LINEA_PTSIN read is equivalent. Unpinned: outlines whose wrapped segments send clip_line into a CYCLE (the ROM never returns; `## Not reconstructed`). Mutation 82/83 (one equivalent `>` → `>=`) |
| `0xfcbbcc` | `vdi_gdp` (VDI opcode 11, `src/vdi/gdp.c`) | 114 | 13 / 258 out of range, 203 / 2306 bar, 924 / 10326 bar outlined, 91235 / 923228 pie, 93369 / 938988 circle, 123686 / 1222218 ellipse, 107077 / 1078928 elliptical pie, 96265 / 1076242 rounded box width 3, 27954 / 278872 filled rounded box, 11470 / 147816 justified | **1.01** out of range, **1.06** bar, a point, xor, **1.04** bar, a point, xor, outlined, **1.01** pie, three quadrants, **1.01** circle, radius 60, filled and outlined, **1.02** ellipse, tall, filled and outlined, **1.02** elliptical pie, tall, wraps past 0, **1.06** rounded box, outlined, width 3, **1.04** filled rounded box, outlined (T→), **1.13** justified, eighty spaces, both spread, clipped away (T→G `glue`) | ✅ verified | the switch at `$fd3954` (signed `ble`/`bge`): all ten arms, and 0, −1, 11, 12, $7fff, −$8000 storing nothing outside the stack band. THE ARMS PROVE BAND 3'S STAGING BYTE FOR BYTE: each arm is run over the staging band 3 used for its worker and its final machine held to the worker's run from that staging (`vdi_gdp.assert_same_machine`, over `harness.differing_addresses`) — so band 3's "machine as the arm leaves it" is now a measured fact: the circle and ellipse arms' scratch to clc_arc's run (perimeter 0 and 1; radii 0/1/−30/32767/−32768; XFM −1..3 for the NDC y radius; each word stored before the next is read, ptsin one word below XC; END_ANG 0 for the ellipse where the circle stages 3600), arms 2/3/6/7 to gdp_arc/gdp_ell over three sweeps and a wide arc, 9 to gdp_rbox, 10 to d_justified (three strings incl. the empty one). The bar: four corner orders, a line, a point; outlined only for WS_FILL_PER EXACTLY 1 (0/2/−1/$0101 not), over vr_recfl's SORTED corners in the fill colour it left in COLBIT, LN_MASK −1 stored before the outline (ptsin[9] on LN_MASK), contrl[1] = 5 last (contrl in ptsin), PTSIN re-read after vr_recfl (ptsin at `$29a2`: the sort moves the pointer); 8's LINE_BEG/END cleared round gdp_rbox and put back (4 boxes × 5 end pairs incl. 3 and $7fff, a virtual record). The worst realistic rows are the ones registered (review A measured them: the width-3 outlined box, the TALL ellipse and wrapping pie). Dead: `$fcbd60`'s `bhi`, `$fcbd5e`'s `bra`. Unpinned: a workstation record over LINEA_PTSIN, and arm 8's put-back through a RE-READ CUR_WORK — its own clears change CUR_WORK only when LINE_BEG/END lie on `$27ca..$27cd`, which makes CUR_WORK 0 (the vector page; the host then faults), so that survivor is recorded unpinned, not equivalent. Mutation (strict, the fixed privlib): 56 — 50 killed, 5 equivalent, 1 unpinned; the perimeter constants' 6 of 6 |
| `0xfcd756` | `v_gtext` (VDI opcode 8, `src/vdi/gtext.c`) | 410 | 23888 / 255990 twelve, 10909 / 104414 fast, 3804 / 40194 one centred, 58790 / 566800 turned, 10 / 206 none, 4879 / 61092 forty clipped, 8401 / 112368 ninety missing clipped | **1.00** twelve characters through TextBlt, **1.00** thirty-eight, the fast path, **0.99** one character, centred, underlined, clipped, **1.00** turned, every effect, three-row underline, **0.42** no characters, **1.01** forty clipped away, proportional, **1.06** ninety missing characters clipped away (T→) | ✅ verified | over REAL fonts (the three ROM faces and GDOS-shaped RAM copies: proportional with a HOR table, a deep bottom, a three-row underline): every H × V alignment in five fonts, italic leans (`mulu.w` LOW word / `divu.w`), the four right angles and other rotations (3600, −900, 450, 1 draw at the STALE DESTX/DESTY, chained through `case.continued`), every effect, the UL_SIZE-row underline clipped row by row with LN_MASK `asr.w` + bit 15, the drop 1 / 0 / −1, DDA scaling, the fast path and all eight refusals, '?' by unsigned bounds, offset/HOR tables sign-extended (HOR ONE BYTE a glyph), justified gaps. GLYPH 0 IS DRAWN IN THE FONT LOADED AT ENTRY (`$fcd76e`; CUR_FONT re-read only after each TextBlt, `$fcdc38` — the review's defect, a font at `$b0010`); the font's lines read after the DESTX store; H > 2 / V > 5 and the non-right-angle underline pinned on the harness's zeroed frame words. Includes 6 host TextBlt scratch refusals and 3 zero-divide refusals (TOP/BOTTOM 0 = the ROM's vector 5). Unpinned: the BOTTOM re-read at 1800/2700 (a header there reads the I/O page). Mutation 143/144 (1 abnormal = the named scratch refusal) |
| `0xfce9e8` | `d_justified` (GDP 10's worker, same) | 59 | 33121 / 330142 turned, 17073 / 182194 one word, 105 / 1812 nothing, 2793 / 36368 clipped, 10964 / 139438, 16164 / 204228, 11444 / 147434 long spaced lines clipped | **1.01** words and characters, turned, **1.00** one word, characters spread, **0.76** nothing to draw, **1.06** clipped away (T→), **1.11** eighty characters, forty spaces, **1.11** a hundred and twenty characters, **1.13** eighty spaces, all three both spread and clipped away (T→G `glue`) | ✅ verified | the slack's `divs.w` over spaces then characters, the remainder made positive IN MEMORY with its sign as the unit; with both flags the word step cut at ± half the widest cell and the cut remainder DROPPED; gaps turned for the right angles (3600 keeps the stale steps, only the counts written); width := length; contrl[3] LEFT at n − 2, contrl[2] := n; ptsin[2] read after vqt_extent and after contrl[2] = 0 (overlaps). The three worst realistic rows (long spaced lines scrolled out of view, the review's) are NET OF THE GLUE 0.99, 1.00 and 1.02. Divergence, documented: at a non-right-angle rotation the ROM's gap steps are vqt_extent's stack LEFTOVERS, the C's 0 |
| `0xfcd402` | `init_wk` (the opens' record set-up, `src/vdi/workstation.c`) | 65 | 443 / 4422 GEM's open, 455 / 4540 a pattern fill | **1.07** GEM's open, **1.07** a pattern fill | ✅ verified | intin[1..10] clamped in intin's order, intin and the record loaded once; line type 0 stored as −1; the FILL STYLE stored 1-BASED (vsf_style stores it less one, so a fresh workstation's pattern is the one after — ROM bug, pinned); DEV_TAB[13] read at the compare; intin over the record reads the stores before it; counts, then intout, then ptsout (its pointer reloaded), a forward word copy; contrl/intin/intout/ptsout tagged (the 24-bit bus), the host core alone over them returning in a child. The interior and fill-style clamps stay spelt out: through `vdi_within_or` they cost 2–4 cycles (high bound compared first) |
| `0xfcb694` | `v_opnwk` (opcode 1, same) | 19 | 23674 / 395360 low, 23052 / 388334 medium, 22915 / 386888 mono | **1.01** low kept, **1.01** medium kept, **1.01** mono kept (T→) | ✅ verified | tables from the ROM defaults (copied before intin is read), INQ_TAB[14], RAM font headers, ring[1]; medium/mono patches (mono makes the 8x16 the default); handle 1 alone and current; text_init, init_wk, modes, M_HID_CT, GCUR, init_timer_mouse; REQ_COL = vq_color REALIZED per colour over a host-slot frame (16 / 4 / 2 declared palette reads; the map's "`$fd2e84`" callee IS vq_color). The two SWITCHING arms halt in Setscreen with the child image equal to the ROM's at the checkpoint (savptr excluded on the ROM side only; ours must be as staged) |
| `0xfcd612` | `v_opnvwk` (opcode 100, same) | 6 + 3 | 488 / 5132 first, 497 / 5232 a second 3, 29 / 552 refused | **1.07** the first, **1.07** a second 3 inserted (T→), **1.17** Malloc refused (T→G `glue`) | ✅ verified | Tier 1 through the REAL `trap #1` into the ROM's GEMDOS (ours on the host); the list built by CHAINED runs, never fabricated (a chain pin holds the rows' staging to it): the lowest handle in LIST order, linked after the record the walk stopped at, so 1,2,4 → 3 appended and the next open a DUPLICATE 3 (ROM bug, pinned); Malloc asked for 308 (spied); Malloc failing answers contrl[6] = 0 and links nothing. Tier 3 over the STAGED recording `trap #1` (an appending ledger), `[$2848, $284c)` LINEA_RETSAV dropped there only — the 3 companions run each row's pokes with nothing dropped. Refused row NET OF THE GLUE 0.90 |
| `0xfcd6a4` | `v_clsvwk` (opcode 101, same) | 5 + 2 | 11 / 206 handle 1, 38 / 674 middle, 42 / 728 last of four | **0.63** the physical workstation (T→), **1.12** the middle one, **1.10** the last of four (T→G `glue`) | ✅ verified | handle 1 refused (no trap); the walk crosses 0 / 1 / 2 links and the FIRST match wins (closing the second 3 of 1,2,4,3,3 drops the first 3 off the list, still allocated); the record relinked, then Mfree; the whole ordered trap ledger compared. Staged `trap #1`, RETSAV dropped at Tier 3 only, companions as v_opnvwk's. NET OF THE GLUE 0.91 and 0.91. Unpinned: the not-found walk (no end test — it wanders through address 0's vectors; no dispatcher call reaches it) |
| `0xfcb998` | `v_clswk` (opcode 2, same) | 2 + 1 | 4366 / 119510 none open, 4447 / 121142 four open | **1.01** none open, **1.01** four open (T→) | ✅ verified | every record after the physical one Mfree'd IN LIST ORDER through CUR_WORK (left 0) — the four Mfrees pinned in order by the appending ledger (a swapped-order mutant survived the single-slot one); the physical WS_NEXT left naming freed memory (ROM quirk); restore_timer_mouse. The four-open row over the staged trap, RETSAV dropped at Tier 3 only |
| `0xfc427a` | `vdi_escape` (VDI opcode 5 — in the BIOS's range, under `vdi` because its code is `src/vdi/`, as `clear_span`'s is; SHIPS as `src/vdi/escape.S`, 4 byte-pinned spans + 13 thunks into `src/bios/vt52.c`; its C twin `src/vdi/escape.c`) | 203 C twin + 92 transcription | C twin 11 / 150 past the table, 19 / 244 vq_chcells, 14155 / 168060 v_exit_cur, 289 / 2954 v_curup drawn, 25096 / 325642 v_curtext line and scroll, 45 / 808 v_hardcopy, 34 / 744 v_fontinit; `.S` 13 / 190 past the table … 25111 / 325780 v_curtext | `.S` **1.00** on the 14 rows that are the escape's own code (the three NOTHING rows, vq_chcells, vq_curaddress, vq_tabstatus, v_rvon, v_rvoff, v_hardcopy, v_dspcur ×2, v_rmcur ×2, v_fontinit); the 24 `.S` rows that reach the console's C **1.31**–**2.43** as shipped, verdict `own` (T←); the C twin **1.09** v_hardcopy, the rest (T) `transcribed` | ✅ verified | THE `.S`: $fc427a..$fc42e5 (dispatch, the 20-word table, the two compares past it, v_offset), $fc442e..$fc4463 (vq_chcells, v_hardcopy, v_enter/exit_cur), $fc44dc..$fc455f (vs_curaddress, v_curtext, rv on/off, the two inquiries, v_dspcur, v_rmcur), $fc4a42..$fc4a9d (v_fontinit) pinned word for word with 27 exact relocations (the 20 table words as displacements from the TABLE — a new `Relocated.base` — eleven to arms, seven to console thunks; seven branch extension words); ESC E's thunk laid at the ROM's own body address so v_exit_cur falls into it and v_enter_cur's `bsr.s` reaches it; the `jmp`s to v_show_c/v_hide_c keep the ROM's addresses (CODE entries). The transcription relation over 55 cases with each ARM's register mask the measured union of what the two sides disagree in (the inquiries, v_hardcopy and v_fontinit clear nothing; the arms reaching the console's C its scratch); contract `d2-d7 a2-a5`, the ROM console's. Tier 3 by the DERIVED (T←) rule: own instructions 1.00 on 19 of the 24, 0.85 on the five edge rows (ESC A-D and J refuse through `beq.s $fc444e`, vq_chcells' `rts` INSIDE the span: 16 console cycles counted as the escape's), the rest carried by five cited `bios_bconout` acceptances. THE C: the dispatch's UNSIGNED `bhi` (negative words and $8000 fall past the table; $0101/$0165/$0166 do nothing) and all 22 arms incl. the undocumented 101 v_offset and 102 v_fontinit; the nine console arms entered by name and proved to be ESC's own table entries; vq_chcells columns-before-rows over contrl and over the console's own geometry; vs_curaddress's unchecked `subq` (0 → $ffff) and the N-flag clamp's exact $8000 boundary; the console cell address WRAPPED on the 24-bit bus (rows 0 and $ccce, ESC Y below the bias — the latent Bconout divergence this band found); v_curtext through the live state machine (controls, ESC Y across two calls, the `dbf` count unsigned at $8000, read-after-draw with intin on screen); v_offset read under the lock and not re-placing the cursor; v_fontinit on the ROM's three fonts, field order pinned by two headers over the console block; v_dspcur clearing the caller's intin[0] before v_show_c; v_hardcopy through the real `trap #14` → Scrdmp into a RECORDING `scr_dump` (one call, `_dumpflg` set after it). Unpinned: column 0 with the cursor drawn (past 1 MB even wrapped; host refusal), a zero-divide v_fontinit (vector 5; host refusal), the real printer dump, an odd intin pointer. Mutation (strict): C 66/68 + 2/2 Scrdmp order and count (+1 ABNORMAL: the bus-wrap revert, caught by the host abort); `.S` 8/9 on a private blob (1 equivalent); a spill in the `.S`'s own code reds 26 of 38 rows |

## Verified — aes (291)

The AES (`$fe387c..$fee8ff`, `src/aes/`), started 2026-09-30 on a read-only map of the whole GEM range and a FOUNDATION
every later port builds on: `include/aes/{aes,objects}.h` (GEMBSS, THEGLO's tables, the object layer, the resource header, the
Line-F mechanism — every field cited to a ROM access and width-tagged), `test/aes.py` (the door: `leaf_machine()` stages the
shell's PD running over a snapshot taken inside disp's idle loop; trees by shape or out of the AES's own relocated resource;
`run_function` DIRECT — the priced row — or THROUGH LINE-F at a staged caller that makes the ROM's own call word; the Line-F
handler's self-patched mask word `$cc44` dropped by name, and at Tier 3 with its undropped companion). Every AES case runs
POISONED — the kit leaves a vetted drop out before it decides to run the attribution pass — but for the Tier 3 companion
(`aes.COMPANION_UNPOISONED` says why) and the cases that opt out ONE BY ONE, each with the reason forcing the pass on
measured (a routine that reads back the link or ledger pointer it stored); answer words are staged stale, and every pointer argument is also handed in
with a top byte (`aes.BUS_TAG`).

BANDS 0+1 (2026-09-30) add the LEAVES and the OBJECT/RESOURCE layer — 90 routines over eleven source files, 1,569 tests in 19
batteries (`test/test_aes_*.py`) plus the staging modules `test/aes_{strings,objects,rlist,resource}.py`. The "optimize" layer's
hand-68000 helpers whose C measured over the bar ship as the ROM's own words in ONE `src/aes/optimize.S` (regions
`$fecb6e..$fed18d`, 32 entries, and `$fe3db4..$fe3ea5`, Alcyon's lmul/ldiv), byte-pinned by `test_aes_strings_asm.py`; every
caller's pointer reaches memory through ONE bus accessor family (`m68k_idioms.h`: `bus_span` and `bus_{byte,word,long}` /
`set_bus_*`), which REFUSES BY NAME on the host what the 68000 could not do — a word or longword at an odd address (the address
error, vector 3, which the oracle's Musashi does not model) and an access running past the top of the 24-bit bus. "Cases" below
counts each routine's registered rows (priced, their `.S` rows, and its unpriced Line-F door); the Tier 1 tests are the
batteries'.

BAND 2 WAVE 1 (2026-10-01) adds THE BRIDGE and what needs no drawing — 27 ✅ routines and two unpriced glue calls over four
files: gemgsxif's atoms (`src/aes/gsx.c`; the five Line-F-free ones also as the ROM's own words in `src/aes/gsx.S`), the shell's
find and the resource load (`src/aes/shell_find.c`, `gemdosif.c`, `resource.c`), and newrect with its window helpers
(`src/aes/wrect.c`). THE AES's ONE `trap #2` is gsx2's: the host checks both hops and runs the VDI's C twin with the VDI's C
cores bound per case, the target makes the real trap, so every graphic AES case compares the WHOLE image — the screen
included — with the ROM's VDI on one side and the reconstructed VDI on the other (a second differential of the VDI). Its Tier 3
rows are mechanism (V) "through the OS": the ratio printed is the row's OWN (our blob less its thunks against the ROM's AES text
and Line-F handler; the trap path and the VDI, which both sides run from the same bytes, in neither), `net` when the own ratio and
the own-with-thunks ratio are both within the bar, `glue` (as T→G) when only the own one is.

BAND 2 WAVE 2 (2026-10-01) adds GRAPHICS OVER THE VDI — 54 ✅ routines over four files: the rest of gemgsxif
(`src/aes/gsxif.c`: the start-up with REAL opens of the physical workstation in all three ST modes, the graphics mode, the mouse's
interrupt routines, the mouse form, the save-under buffer and its blits, the mouse state; gsx_mret, ratinit, gsx_mxmy and
gsx_button also as the ROM's own words in `src/aes/gsxif.S`), gemgraf (`src/aes/gemgraf.c`; gr_inside, gr_crack, gsx_gclip,
gsx_chkclip and gsx_bxpts also in `src/aes/gemgraf.S`) and gemgrlib's non-interactive animations (`src/aes/grlib.c`). THE
`$a000` HALF OF THE BRIDGE (`gsx.h`'s `gsx_linea_base`, gsx_mfsave's Line-A init): the host checks vector `$28` → the ROM's
Line-A dispatcher `$fc9f0c` and halts by name, then runs the VDI's linea_init C twin and answers A0; the target makes the real
`$a000` word. Every graphic case compares the whole image, screen included, against the ROM's VDI. gsx_call became one inline in
gsx.h (no row moved).

BAND 2 WAVE 3 (2026-10-01) adds THE OBJECT DRAW PATH and COMPLETES BAND 2 — 6 ✅ routines over three files: the leaves
(`src/aes/obuser.c`: ob_format, far_call, ob_user, with `staged_call.h`'s call_alcyon_pointer now answering D0), the per-object
drawer just_draw (`src/aes/objdraw.c`, over its ROM frame in one host slot, its two jump tables as two `switch`es) and the tree
walkers ob_draw and ob_change (`src/aes/obdraw.c`). ob_draw hands everyobj just_draw BY VALUE, as the ROM does: on the host the
value is the ROM address the case's hook binds to the C core; on target it is `src/aes/obdraw.S`'s ALCYON ENTRY (target-only
GLUE, not a transcription: `atari/target.mk`'s ALCYON_ENTRY_SOURCES, counted by Tier 3 as glue through `tier3.ALCYON_ENTRIES`),
because the (V) bench refuses a row in which our build runs the ROM's AES code. Every cell is drawn over the snapshot's own trees
(the AES's and the desk's resources, the menu bar, the desk's icons, the window tree) or staged on a real object where no data
reaches it; the machines a draw starts from are DERIVED from ROM runs (the IBM font as the ROM's own gsx_tblt leaves it, the
whole screen's clip as gsx_sclip(gl_rscreen) does — `case.written_by`), never poked.

BAND 3 WAVE 0 (2026-10-02) opens FORM / MENU / WINDOW with THE EVENT DOOR — 38 ✅ routines over five source
files and the door's own `src/aes/evdoor.c`. Band 3's C calls the event layer and the scheduler (ev_multi, ap_rdwr;
wave 1 adds tak_flag, unsync, ev_block, ct_chgown and
post_button; wave 2 adds ev_button), which are band 4's and have no C yet, so every such call goes through ONE wrapper per entry in
`include/aes/evdoor.h`, keyed by the ROM address: on target an inline Alcyon call (the frame pushed once, a `jsr` to the ROM's
own routine), on the host a NESTED ORACLE RUN of the ROM's band-4 routine over a copy of the candidate's image
(`test/aes_event.py`: its writes laid back, its D0 answered, every frame it is handed compared with the frame the ROM's own run
hands the same entry). The door REFUSES by name, halting the core, rather than answer: an entry not served, a moved Line-F hop,
a run touching the hardware or past its measured cap, and a run that reaches the dispatcher — a call that WOULD BLOCK, which
the snapshot's indisp = 1 would otherwise turn into a "no event" no process can see. When band 4 ports the event layer, each
wrapper's body becomes the call of its C twin, and the rows stop being door rows by derivation. Tier 3's mechanism (EV)
prices such C on its own cycles: our run and the ORIGINAL's are both watched at the door's entries, each door call a window
taken off the ROM's own, the two sides' windows asserted equal (cycles and frames), and an AES cycle of ours outside a window
refused. THE MACHINES ARE THE SCHEDULER'S OWN: a running process is made by delivering the event a parked process waits for
and running disp's loop (`$fe4dda`: forker, idle, switchto) until the woken process leaves its evnt_multi (`$fe6c5c`) — PD0
by the Return key or the left button, PD1 (the screen manager) by the mouse on the menu bar — never by poking rlr, indisp,
PD_STAT or the lists. Beside the door's pilots (`src/aes/grwait.c` gr_stilldn and gr_watchbox, `apmsg.c` ap_sendmsg, `ctrl.c`
ct_mouse — a band-4 leaf with no door), two slices needed no door: the object editor (`src/aes/obedit.c`, ob_edit and its ten
gemobed helpers) and the window library's non-blocking half (`src/aes/wmlib.c`, 23 routines over machines derived from the
ROM's own wm_create / wm_open / wm_set).

BAND 3 WAVE 1 (2026-10-02) adds the WINDOW MESSAGES AND UPDATE and the INTERACTIVE half: 29 ✅ routines over three
source files. `src/aes/wmupdate.c` holds 13: the control manager's set_ctrl / get_ctrl / get_mown, fm_own, w_setactive,
w_redraw, w_update, draw_change, wm_opcl / wm_open / wm_close / wm_set and wm_update. `src/aes/grdrag.c` holds gr_wait
(gr_draw and gr_xdraw folded), gr_clamp (its fragment `$fe86c2` folded), gr_rubwind, gr_rubbox, gr_dragbox and
gr_slidebox — every reader of gr_wait's `$fe8586` immediate, gl_rzero BY VALUE. `src/aes/mnlib.c` holds rect_change, do_chg,
menu_set / menu_sr / menu_down, mn_do, mn_bar, mn_clsda, mn_register and the scheduler's leaf pd_nameit.

THE DOOR GAINS FIVE ENTRIES, each with one wrapper, one `ENTRIES` line, one census line and a measured dsptch-free answered
call (`test_an_answered_call_of_each_entry_reaches_no_dispatcher`):
- tak_flag `$fe4e5a` (the SPB read whole);
- unsync `$fe4eb8`;
- ev_block `$fe6874` (code word, parameter long);
- ct_chgown `$fe49ba` (owner, GRECT read);
- post_button `$fe52e2` (pd.l, button.w, clicks.w — mn_bar's fake click).

ev_multi gains its second TARGET shape: TWO rectangles, the timer and message pushed as zero by `clr.l`, as mn_do does. It
is priced by mn_do's three rows. ev_block has no answered row: its only door user calls it after tak_flag refused the same
semaphore, so it always waits (`NEVER_ANSWERED`, pinned by the blocking case). ev_button joined in wave 2.

The nested run's cap is now `NESTED_RUN_INSNS = 40,000`. That is a margin of 20 checked AT RUN TIME inside `nested_run`, over
the deepest call measured: mn_do's interrupted two-rectangle ev_multi, 1,697 instructions, pinned exactly as `DEEPEST_INSNS`.
`DERIVATION_INSNS` is 1.5 M (deepest derivation 244,097, draw_change of a lower window resized).

The door no longer lays back a nested run's write to the Line-F mask word `$cc44`. A routine making its own non-empty masked
return after its last door call rewrites the word itself, and Tier 3's undropped companion must see a C that writes it.

INTERRUPTS DELIVERED AT A DOOR ENTRY (`aes_event.interrupted`) pin the states a loop reaches only when the mouse or button
changes while it runs. The ROM's watched run is stopped at the k-th door entry, and the ROM's OWN interrupt code (the VDI's
mouse ISR and the tick glue) runs over the memory there, its stack frames left out. The bytes it wrote are laid in at that
entry on the ROM's side, and identically into the C's image at the same ordinal in a child.

The returned-or-blocked outcome, the answer, every handed frame and the whole image are compared. RED proofs: the delivery
dropped on either side, or shifted one ordinal, reds. This obeys THE PRINCIPLE: an interrupt arriving inside an event call
is a reachable interleaving, and its effect is the ROM's own ISR over the ROM's own memory, never a poke. Tier 3 prices
these rows since wave 2 (below).

Calls the dispatcher would switch on are refused by name in two kinds, matched by the dispatcher's own words
(`aes_event.BLOCKS` / `YIELDS`):
- a call that WOULD BLOCK leaves its process waiting;
- a call that WOULD YIELD keeps the caller ready but switches, as unsync does when it hands the lock to a queued waiter.

`refused_where_the_rom_blocks` compares the child's WHOLE image with the ROM's at the refusing entry, and `returns_in_a_child`
runs a looping door user's C in a child first (30 s). The machines are the scheduler's and the ISR's:
- PD0 running by a key or the button, the mouse moved first, or the cursor SHOWN (`shown_machine`, the snapshot's own state);
- PD1 woken onto the menu bar, then moved or pressed by interrupts — moves keep a held button;
- a process PARKED in its own evnt_multi while holding the lock (`aes_event.parked`);
- accessories registered by the ROM's mn_register.

The host slots' held flags are now an array of bytes, `host_slots_held[HOST_SLOT_ID_COUNT]` (the 64-bit mask was full at 60
of 64). The routine handed by value is one macro, `ALCYON_ROUTINE` (`staged_call.h`); objects are byte-identical.

BAND 3 WAVE 2 (2026-10-03) adds THE FORMS AND THE ALERTS: 16 ✅ routines over two source files. `src/aes/fmlib.c` holds
the event-free half (8): gemfmalt's fm_strbrk / fm_parse / fm_build (an alert string split into the alert tree, the tree
laid out), gemfmlib's find_obj / fm_inifld / fm_keybd, and the event layer's keyboard-queue leaves dq / fq. `src/aes/fmdo.c`
holds the forms that wait and the alerts (8): fm_button, fm_do, fm_dial, fm_alert, fm_show, eralert, fm_error and fm_do's
bell (`$fe3a0c`, BIOS Bconout by `trap #13`). Every alert string and every dialog of both resources is the data; the
machines are derived — fm_build over the ROM's own fm_parse of each alert, a key queue filled by keys typed through the
BIOS handler and polled by the ROM's chkkbd + forker, the desk's dialogs centred by the ROM's ob_center, window drawing
held by the ROM's own wind_set, the keyboard handed to PD1 by the ROM's ct_chgown, a stale DEFAULT left by the ROM's own
fm_alert(-1, …) run.

THE DOOR GAINS ITS SIXTH ENTRY, ev_button `$fe68a4` (clicks.w, mask.w, state.w, answers.l) — fm_button's wait for the
rise: one wrapper, one `ENTRIES` line, one census line and a measured dsptch-free answered call. Every entry band 3 needs
is now wrapped.

INTERRUPTED ROWS ARE PRICED AND FULLY VETTED.
- A row may carry the interrupts it is taken through: a ninth VERIFIED_CASES field, `{door call: (found, wrote)}`.
- Every run of its original lays them at the same door call at no cost: the measure's original and the windows run (the
  kit's `watched_original` / `RomBench.measure(original_watch=)`, the bench write ledger `emu.bench_writes` keeping the
  mask word's drop vetted), our blob, the shipped blob, and the snapshot's sweeps (`aes_event.replayed`). Each delivery is
  checked against the memory it lands on, and a call that reaches dsptch is refused by name on every watch.
- One run of the routine computes every delivery (set aside and continued at each entry): linear where it was quadratic,
  equal byte for byte on the 24 earlier cases. A registered row derives its deliveries once, pinned equal to a
  re-derivation over its settled machine.
- 16 interrupted rows are registered: wave 1's mn_do 0.63, gr_dragbox 0.80, gr_slidebox 0.75 and gr_rubwind 0.80, fm_do's
  11 and fm_alert's 1.
- EVERY interrupted case whose ROM run returns, registered or not, takes the bench's second differential inside
  `aes_event.interrupted` — callee-saved registers, odd accesses, the write-ledger-vetted drop, both sides' refusal tallies,
  streams and the whole image. It is derived by the code path, not listed: 56 today (fm_do 27, fm_alert 7, eralert 1,
  mn_do 6, gr_watchbox 5, gr_dragbox 3, gr_rubbox 2, gr_wait 2, gr_rubwind 1, gr_slidebox 1, newrect 1).

KEYS ARE DELIVERED THROUGH THE BIOS KEYBOARD ISR, IN ONE WATCHED RUN. `aes_event.key(scancode)` is an interrupt like
`press`: the BIOS keyboard handler run at the door entry (`scancode_of` reads the snapshot's own unshifted Keytbl).
`typed` delivers the next key at each ev_multi entry, proved on the ROM's own fm_do: "abc\r" typed one per wait leaves the
memory byte-identical to the run with every key in the ring up front. `aes_event.Waits` delivers at the k-th call of an
entry whatever door calls come between (the entry checked at every call, the count per run); `double_click` is three
packets inside the click delay through the VDI mouse ISR, then the ticks.

THE STORE ABOVE RAM IS REFUSED BY NAME. The bus accessors (`m68k_idioms.h`'s `set_bus_byte` / `set_bus_word` /
`set_bus_long`, the one family) refuse on the host a store any byte of which is at or above `ST_RAM_BYTES` (`$100000`):
the oracle drops such a store and an ST loses it or takes a bus error, while the host C would write its image. fm_strbrk's
5th button or 10th line reaches it (`$ff1100`); the screen (`$f8000` + 32,000) lies below the bound (pinned). Reads are
untouched; on target the store is the plain one.

CHIP SEEDS ARE DECLARED BEFORE EVERY BENCH RUN. Every bench entry of ROM code — watched originals, `parked`, the continued
runs — declares "nothing" for the PSG and the named hardware (`emu.install_chip_seeds`) and enters with `emu.run`'s
register file (`rom_bench.original_entered`). A seed or register file the previous run left reached the next before:
measured, a watched original read another case's GPIP seed unrefused, and `parked`'s machine differed in 94 bytes by what
ran before it.

BAND 3 WAVE 3 (2026-10-03) adds THE FILE SELECTOR and completes band 3: 11 ✅ routines and one ⚠️. `src/aes/fslib.c`
holds gemfslib whole — fs_start, fs_back, fs_pspec, fs_active, fs_1scroll, fs_format, fs_sel, fs_nscroll, fs_newdir and
fs_input (`$fe7d90`, AES opcode 90, fsel_input); `gemdosif.c` gains dos_snext and the bell's Cconout glue.

EVERY MACHINE IS THE ROM's OWN fs_input. The snapshot holds no selector state (its three block pointers are 0), and
nothing is poked: the ROM's fs_input is run over the scheduler's running PD0 and a staged RAM disk into the ROM's REAL
GEMDOS and stopped where a routine is entered (`aes_fslib.entered`, just past its `link`; `listed`, where the first
fs_newdir has returned), the case's arguments read off the ROM's own frame. The disk is thirteen directories, one per
shape — 0, 1, 9, 10, 99, 100 and 101 names; sorted, reversed and shuffled; folders among files; one name held three
times — and four more disks, each the first plus ONE folder, so no machine over the first moves.

GEMDOS REPLAYED is what Tier 3 prices over. Real GEMDOS cannot be priced (the trap entry's register save is the
caller's, different by nature), so a staged `trap #1` handler answers a script — D0, and for a search the 44 DTA bytes —
derived by calling the ROM's own GEMDOS, call by call, over the memory as it stood at each call, and records every
frame in a ledger the differential compares. A replayed run is held to the real disk's wherever the selector can see
GEMDOS. The AES staging window grew to 24 KB (`WINDOW_BYTES` `$6000`) for the script.

fs_input's CASES ARE SESSIONS — the routine taken through what a user does at each wait (`test/aes_fs_sessions.py`: a
schedule per wait, each click placed by the ROM's own ob_offset), every interrupt the ROM's own ISR's, GEMDOS replayed
from the ROM's own run of the same session. 80 return and 20 are cut short at a wait. Each is held four ways:
- the whole image at the end;
- the image where the ROM blocks (the C refused at the same call — the selector still on the screen);
- every VDI call in order (opcode, intin, ptsin);
- what the selector HOLDS as each VDI call is made (`aes_fslib.held_in`: its tree's 25 objects, the texts of its three
  fields and nine rows, its two scratches, the two paths — about 450 points a session), which is what sees a tree word
  set and put back between two waits.
Real GEMDOS on both shores, in process, covers what only one run can make: keys typed ahead, the three no-memory arms
(the arena exhausted by the ROM's own Malloc), Line-F — with the glue's parked return addresses held at every call.

A LONG CASE DECLARES ITS BUDGET, AND A SESSION IS PRICED BY ITS SLICES.
- `budget=` on a case: its derivation's budget and that run's cap, held both ways by name over a run of N instructions —
  NEEDED (5N above `DERIVATION_INSNS`, whatever the declaration's size), FITTED (5N <= B), NOT STALE (B <= 10N). The
  default (1.5 M) is untouched. `cap=` is the in-process differential's own limit, held the same way against
  `emu.run`'s 200,000. A registered row keeps its budget for every later derivation.
- `aes_event.register_slices`: one priced row per SLICE, the run between two ARRIVALS both shores make at one PC — a
  door call, a trap taken (a VDI or GEMDOS call: fs_input makes no door call for its first ~350,000 instructions), the
  entry, the return. Both shores run the WHOLE session, marked at the two ends; our run must arrive at each after the
  same door calls and with the ROM's memory, and each slice is at most `SLICE_INSNS` (200,000) of the ROM's own.
- THE PARTITION TEST (`tier3.uncovered_stretches`) cuts each sliced session whole — at every door call and every
  registered slice's ends, the pieces summing to the run to the cycle — and holds every stretch no registered slice
  covers at or under the routine's worst registered row. A dear stretch is registered, or the test reds.
- fm_do's 38-key session (5 slices) and six fs_input sessions (34 slices) are priced so; fs_input's three no-memory
  arms are plain rows.

69 priced rows for the eleven routines, 37 of them fs_input's, and 5 more for fm_do. Worst per routine: fs_back 1.04
(a path of 79 characters with no separator, the longest the selector holds: the per-byte scan, 70 cycles against 64),
dos_snext 1.01, fs_input 0.96 (the close box's arm alone over a root with no drive: the ROM's own 849-byte defect
scan), fs_pspec 0.96, fs_format 0.88, fs_active 0.83, fs_newdir 0.82, fs_nscroll 0.80, fs_sel 0.65, fs_start 0.59,
fs_1scroll 0.42. With their thunks counted back: fs_input 1.00, fs_active 0.94, fs_newdir 0.93, fs_nscroll 0.90,
fs_sel 0.70. fm_do's worst is now 0.77, the last character of its 38-key session.

`fs_input` WITH A DIRECTORY TO READ AND AN EMPTY WORKING PATH NEVER RETURNS in the ROM — `fs_input("")`, and a second
road through the close box. The target build does the same; the host build refuses the pass by name (a DIVERGENCE:
`## Not reconstructed`). Every other ROM defect is reproduced byte for byte.

BAND 4 WAVE 0 (2026-10-04) opens THE EVENT LAYER, THE SCHEDULER AND THE INPUT — what lies behind the event door — with
the door made REBINDABLE and its first entry rebound: 18 ✅ routines over three source files. `src/aes/evsync.c` holds
tak_flag (`$fe4e5a`), the screen lock's semaphore and THE FIRST REBOUND DOOR ENTRY; `src/aes/evasync.c` gemasync's
lists — signal, azombie, get_evb, evinsert, takeoff, apret, acancel — and geminput's evremove; `src/aes/pdpipe.c` the
PDs and the pipes — pd_match, fpdnm, getpd, pstart, doq, aqueue, ap_find — with gemdosif's uda_insuper and psetup,
which ship as `src/aes/pdpipe.S`.

THE BAND, AS SCOPED (read-only, over the band-3 tree): 81 routines / 7,074 B — not the map's ≈9 KB, which counted all
of gemdosif where its scheduler part is 298 B — calling NOTHING unported. Six are ✅ already (set_ctrl, get_ctrl,
get_mown, dq, fq, pd_nameit) and one is dead (`$fe395c`): 74 to port. What the scoping measured, and the plan stands on:
- A REAL PROCESS SWITCH IS ONE RETURNING ROM RUN, AND CHEAP: PD0's ev_multi(MU_KEYBD) with no key is 920 instructions
  to dsptch, 90 through dsptch / disp / savestate into disp's loop, 1,640 more to the `rte` back into PD0 once Return
  is delivered while the machine idles, 212 for ev_multi's tail — 2,862 instructions / 42,846 cycles whole.
- NO BAND-3 ROW REACHES dsptch (the door refuses it by name), so rebinding the eight wrappers needs the event layer's
  C and a dispatch hook that keeps refusing — not the switch, which later only ADDS rows and moves none.
- Two processes give almost every multi-process situation; a third is needed for two waiters on one list, two
  pending delays, a message to a third pid.
- The Line-F handler is 36–38 % of the ROM's own cycles in the event layer; the hand-asm switch is 3.5 %.
- THE PREDICTION: all 152 (EV) rows re-priced with the event layer added back to both sides put NO row over 1.10 for
  a layer costing anything up to 1.10x the ROM's; at the 0.45–0.80 the already-ported leaves measure the median moves
  0.75 → 0.71–0.76. Flip 1 (below) is the first check of it: no moved row over 0.82.

THE RULINGS (the orchestrator's, on the design's open questions — the band's decisions):
- Q1 THE HOST'S MODEL OF THE SWITCH: REFUSE at dsptch for waves 0–2 — the dispatch hook refuses by name, a block told
  from a yield, the child's image compared with the ROM's at dsptch; the real C scheduler model (the switch back to
  the same process a return, a foreign process a nested ROM run) lands with wave 2's dispatcher slice / wave 3.
- Q2 A THIRD PROCESS OVER A STAGED STUB made by the ROM's own pstart is ALLOWED as a labelled machine class, "a staged
  application": Tier 1 only, never cited in a "realistic" claim, the stub three instructions making one Line-F call.
- Q3 FORK-FUNCTION ADDRESSES: the host stores the ROM's (the image exact at Tier 1; forker's `jsr (a0)` through ONE
  `staged_call.h` hook), the target its own entries (a Tier-3-only named drop of the queue's fcode longs), deliveries
  relocated when laid into our blob.
- Q4 WHAT SHIPS AS ASM: disp as the ROM's stream with its six Line-F call words as `jsr`, under a new project-side
  transcription kind; dsptch, savestate, switchto, gotopgm, the two spl, cli, sti and the irq glue byte-exact `.S`. A
  context switch has no C spelling — this is inside the project's "C first, `.S` where C cannot meet the bar" policy,
  not an exception to it. psetup / uda_insuper: C first (measured over the bar this wave; they ship `.S`).
- Q5 THE BAND'S EDGE as the design states it: gotopgm transcribed now, its row with band 5's accessory.
- Q6 RE-PRICING IS ACCEPTED UP FRONT: a moved (EV) row is expected. THREE flips are THREE commits (tak_flag the
  pilot; the six; ev_multi alone), each with the table saved before and after and every moved row listed old → new
  with the predicted band beside it. A row landing OVER 1.10 is NOT accepted by this ruling.
- Q7 NO KIT CHANGE; one that proves necessary is its own commit with the kit's and the six project suites.
- `$cc44` stays a dropped word: the Line-F handler's RAM copy is not reconstructed in band 4.

THE DOOR IS REBINDABLE, AND tak_flag IS REBOUND (FLIP 1). The hook has a third answer, ARRIVED: a rebound entry's
wrapper still packs its frame and asks; the case records the frame and lays the interrupt due at that call; then the
C twin runs, on both builds. Which entries are rebound is DERIVED (the host's from the library's exports, Tier 3's
from the blob's symbols, held equal). While a flip is in flight the entry is SHADOWED — the ROM routine's nested run
over a copy at the arrival, the twin held to it at its return. At Tier 3 a rebound entry's call is still an ARRIVAL
(ordinals, deliveries, slice marks, frames held equal) and opens NO window: the ROM routine's cycles are the ROM's own,
the twin's ours. The flip moved 88 committed rows — every one a row that takes the lock or runs wm_update's re-compiled
body — by the ROM's 364 / 384 / 376 cycles a call (its routine and its Line-F return) against the twin's 226 / 214;
the highest moved row is 0.82 and no verdict changed. The dispatcher has a host hook that refuses by name.

A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION — the rule the pilot's review
measured, and every later flip is held to (the wave log has the numbers).

EVERY MACHINE IS A ROM RUN'S. The lists' cases are ARRIVALS — the ROM's own run of a scenario watched at the eight
routines' entries, each call verified from the machine and the frame the ROM makes it with (187 calls in 20
scenarios). The pipes' are ap_rdwr's and iasync's own, a writer parked by its own blocking write, and — for the states
past the ROM's invariants — the ROM's own pipe overrun and negative index. A third process is the labelled STAGED
APPLICATION, Tier 1 only: no row of any registry runs over one, and nothing learnt on one is quoted as what a real
third process does.

50 priced rows for the 18 routines and 5 `.S` rows. Worst per routine: doq 0.98 (a read of a whole full pipe: the
longest copy, the C's saving a constant), get_evb 0.83, apret 0.79, pd_match 0.79, acancel 0.78, signal 0.77, pstart
0.76, aqueue 0.74, getpd 0.72, azombie 0.63, takeoff 0.63, ap_find 0.60, tak_flag 0.59, evremove 0.57, fpdnm 0.56,
evinsert 0.50. uda_insuper and psetup measure 1.50 and 1.24 in C (the image pointer on a body of four and twelve
instructions) and ship as the ROM's own words, 1.00.

THREE CALLS HALT BY NAME ON BOTH BUILDS where the ROM destroys its own RAM or never returns — doq's read past the
pipe, aqueue's pipe of a process id no PD has, ap_find's name of twelve characters or more (`## Not reconstructed`).
Every other ROM defect found is reproduced byte for byte, the pipe overrun into the next PDs among them.

| address | function | cases | original insns / cycles | Tier 3 | state | what the cases pin |
|---|---|---|---|---|---|---|
| `0xfed382` | `get_par` (`src/aes/oblib.c`) | 3 rows + 1 Line-F | 27 / 398 the root, 39 / 542 the last child, one step, 169 / 2082 the first of 11 siblings | **0.34** the root, **0.52** the last child, one step, **0.65** the first of 11 siblings | ✅ verified | over the snapshot's file selector (the AES resource's tree 0, 25 objects four deep): the first of the root's ELEVEN children (1..7, 21..24 — the walk crosses every sibling), the last (one step), the deepest, three siblings to a parent that is not the root, the last of nine; the root answered -1 by `moveq` with nothing read (a tree pointer into the I/O page); the tree pointer put on the 24-bit bus (a top byte); the SIGNED index — an object whose ob_next is -1 walks to the object BELOW the tree (staged there: a next of 2 whose leaf tail -1 ends it, answer 2; unsigned reads 1.5 MB above and answers -1); the test is ob_tail alone (a sibling whose tail names the child is taken for its parent); direct and through Line-F ($f150). Mutation (strict): 5 — 5 killed; the three that make the host loop where the ROM returns were ABNORMAL (a hung case) until the kit's watchdog ended the spin, and each is now KILLED by failed assertions beyond its crashed tests |
| `0xfea584` | `ob_offset` (opcode 44's implementation, `src/aes/oblib.c`) | 3 rows + 1 Line-F | 85 / 1164 the root, 347 / 4450 the deepest, four levels, 285 / 3594 the first of 11 siblings | **0.34** the root, **0.33** the deepest, four levels, **0.47** the first of 11 siblings | ✅ verified | the screen position over the snapshot's file selector (root, first child, the deepest, the last of nine), both words stored through at every step in the ROM's order: x laid over the object's own ob_y (x += ob_x lands in ob_y before ob_y is read), x over an ancestor's ob_x (doubled, never summed in a register), one word for both; the sums words that wrap ($7000 + $7000); the tree and both answer words put on the 24-bit bus; the answer the walk's last get_par, -1, which the desk's binding hands on ($fde280); direct and through Line-F by the word MOST of its callers use — `$f208` ×4 (the desk's binding at $fde278 and three AES callers, the dispatcher's arm 44 among them), not `$f154` ×3 (the object library's own callers, ob_find and ob_change), both sets of sites pinned by `test_aes_door`. The row once labelled "the first of 24 siblings" is the first of the root's ELEVEN children. Mutation (strict): 8 — 7 killed, 1 equivalent (the two clears swapped: nothing is read between them, and the words cannot half-overlap on a 68000); its answer word without the bus mask KILLED |
| `0xfecd22` | `rc_intersect` (`src/aes/rect.c`, ships as C: under the bar) | 11 rows + 1 Line-F | 33 / 376 a far edge that wraps negative .. 39 / 426 clip inside rect | **0.99** a far edge that wraps negative, **1.01** an extent that overflows but overlaps, **0.98** clip inside rect, **1.09** disjoint across, overlapping down, **0.99** edges touching, **1.00** negative origins, **1.01** overlap to the lower right, **0.98** overlap to the upper left, **0.93** overlapping across, disjoint down, **1.01** rect inside clip, **1.01** the desktop window | ✅ verified | hand 68000 ported to C: every branch of both axes' min and max, both answers; word sums that wrap (a far edge going negative is empty); the answer the V-aware signed compare of the `ble` after `sub.w`, not the stored extent's sign ($9000 to $7000: extent $e000, still non-empty); both axes stored whatever the first found; the y pass reads the x pass's stores (a clip laid one word below the rect); a rect with itself; the snapshot's desktop window, WIN_FULL clipped to WIN_PREV in place; both pointers put on the 24-bit bus; returns by `rts`, so the mask word is never stored (the door's drop drops nothing). THE BUS TOP IS A HOST REFUSAL, not a wrap: the C holds each GRECT pointer once (`grect_at` = the shared `bus_span`), and a GRECT whose last word passes the top of the bus ($fffffa, $fffffe — as clip and as rect) is refused on the host by name (target code unchanged), the last fitting one ($fffff8) served. Its C holds the two pointers as the ROM's `movem` does, settles each origin before the far edge, and recomputes x's answer from x's own stores after the y pass. Its return leaves through the shared tails $fed066/$fed06a/$fed06e (the executed-path check now names all three). Mutation (strict): 14 — 12 killed, 2 equivalent |
| `0xfecb6e` | `mul_div` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 9 / 314 mul_div a slider: 37 of 480 over 1000, 9 / 304 mul_div a zero product | **1.42** mul_div a slider: 37 of 480 over 1000 (T), **1.43** mul_div a zero product (T); `.S` **1.00** ×1 | ✅ verified | a*b/c with the `muls`/`divs` pair, the product's sign and the rounding; /0 a host refusal (vector 5). THE OVERFLOW ARM IS ORACLE-DEFINED: DIVS's N after an overflow is undefined on the 68000 — Musashi keeps muls' N, the machine (Hatari/WinUAE) sets it, so mul_div(1000,1000,1) answers -15808 under the oracle and -15809 on the machine; the C follows the oracle, the shipped `.S` is the machine's own, and no Tier 3 row prices that arm |
| `0xfecbc6` | `set_contrl_ptr` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 1 row + 1 `.S` | 3 / 88 a pointer | **1.54** a pointer (T); `.S` **1.00** ×1 | ✅ verified | contrl[7..8] stored ($c7ee: the pointer a VDI call carries — the parameter block itself is $9466); reached by ap_tplay/ap_trecd (the map's "unreached" range is only $fecb8a..$fecbc5 and $fecbd0) |
| `0xfecbda` | `get_contrl_ptr2` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 1 row + 1 `.S` | 4 / 100 contrl[9..10] | **1.53** contrl[9..10] (T); `.S` **1.00** ×1 | ✅ verified | contrl[9..10] read back through the second pointer ($c7f2) |
| `0xfecbe6` | `lstcpy` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 3 rows + 1 `.S` | 9 / 122 empty, 42 / 408 a name, 771 / 6726 254 bytes | **2.78** empty (T), **2.53** a name (T), **2.47** 254 bytes (T); `.S` **1.00** ×1 | ✅ verified | copy with the NUL, (dst, src); D0.w = the length counted in a BYTE (`addq.b`) minus 1 — a 255-byte copy answers -1; overlap both ways; every pointer tagged |
| `0xfecbfa` | `xstrpix` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 8 / 118 empty, 33 / 308 a label | **1.69** empty (T), **1.87** a label (T); `.S` **1.00** ×1 | ✅ verified | a byte-counted copy (the counter wraps at 256); top-byte tags |
| `0xfecc12` | `wset` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 6 / 106 0 words, 21 / 212 5 words | **1.24** 0 words (T), **1.50** 5 words (T); `.S` **1.00** ×1 | ✅ verified | n words set, 0 words, the counter's wrap; no caller (no Line-F door) |
| `0xfecc28` | `xstrpix_n` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 1 row + 1 `.S` | 22 / 222 4 bytes | **2.30** 4 bytes (T); `.S` **1.00** ×1 | ✅ verified | n bytes, 0 = 65536 (the whole-bank case, `staging.WHOLE_BANK_AT`); no caller |
| `0xfecc40` | `wcopy` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 6 / 110 0 words, 21 / 236 5 words | **1.69** 0 words (T), **2.40** 5 words (T); `.S` **1.00** ×1 | ✅ verified | a forward word copy (a one-word smear up and down), 0 words |
| `0xfecc56` | `wfill` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 6 / 106 a zero value, 15 / 168 3 words | **1.06** a zero value, **1.45** 3 words (T); `.S` **1.00** ×1 | ✅ verified | ROM SLIP pinned: the guard tests the VALUE loaded last, not the count — value 0 stores nothing, count 0 stores 65536 words (the whole bank); no caller |
| `0xfecc6c` | `lstrlen` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 8 / 104 0 bytes, 41 / 390 11 bytes | **1.56** 0 bytes (T), **1.29** 11 bytes (T); `.S` **1.00** ×1 | ✅ verified | the string's length — the map's "strlen+1" is wrong; a 64K string |
| `0xfecc7e` | `lbcopy` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 3 rows + 1 `.S` | 6 / 116 a zero count moves nothing, 32 / 340 disjoint, forward, 71 / 704 overlapping, the destination above | **1.55** a zero count moves nothing (T), **1.88** disjoint, forward (T), **1.91** overlapping, the destination above (T); `.S` **1.00** ×1 | ✅ verified | memmove: backward iff src < dst compared as SIGNED LONGWORDS (top bytes count); ROM finding pinned: a backward count from 32770 up moves ONE byte (the signed word counter); forward and backward overlap by one and by 64K |
| `0xfece2e` | `movs` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 6 / 124 0 bytes, 20 / 278 7 bytes | **1.60** 0 bytes (T), **2.29** 7 bytes (T); `.S` **1.00** ×1 | ✅ verified | n bytes, 0, 64K counts; (count, src, dst) order |
| `0xfece42` | `min` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 5 / 90 ascending, 7 / 110 descending | **1.12** ascending (T), **0.77** descending; `.S` **1.00** ×1 | ✅ verified | signed words both ways, equal |
| `0xfece4e` | `max` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 6 / 100 ascending, 5 / 90 descending | **0.90** ascending, **1.12** descending (T); `.S` **1.00** ×1 | ✅ verified | signed words both ways, equal |
| `0xfece5e` | `bfill` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 7 / 120 0 bytes, 21 / 246 7 bytes | **1.18** 0 bytes (T), **1.96** 7 bytes (T); `.S` **1.00** ×1 | ✅ verified | n bytes of a value, 0, the tagged destination |
| `0xfece74` | `toupper` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 9 / 114 a, 6 / 90 already upper | **0.95** a, **1.20** already upper (T); `.S` **1.00** ×1 | ✅ verified | a-z only, every byte either side |
| `0xfece8c` | `strlen` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 6 / 94 0 bytes, 50 / 468 11 bytes | **1.85** 0 bytes (T), **1.05** 11 bytes; `.S` **1.00** ×1 | ✅ verified | 0 and n bytes; leaves through the bare-rts tail $fed06e (`beq.w`) |
| `0xfece9c` | `streq` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 3 rows + 1 `.S` | 9 / 144 both empty, 41 / 448 equal, 38 / 414 one byte differs | **1.75** both empty (T), **1.74** equal (T), **1.73** one byte differs (T); `.S` **1.00** ×1 | ✅ verified | equal, a byte differing at each end, both empty; the shared tails |
| `0xfeceb8` | `strcpy` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 7 / 122 0 bytes, 35 / 430 14 bytes | **1.80** 0 bytes (T), **2.25** 14 bytes (T); `.S` **1.00** ×1 | ✅ verified | (src, dst); answers dst past the NUL |
| `0xfecec4` | `strscn` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 9 / 138 empty, 19 / 230 up to the stop | **1.84** empty (T), **1.54** up to the stop (T); `.S` **1.00** ×1 | ✅ verified | copy up to a stop byte, empty |
| `0xfeceda` | `strcat` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 15 / 202 onto 0 bytes, 21 / 256 onto 3 bytes | **2.01** onto 0 bytes (T), **2.09** onto 3 bytes (T); `.S` **1.00** ×1 | ✅ verified | onto 0 and n bytes |
| `0xfeceee` | `scasb` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 7 / 106 empty, 33 / 322 found | **1.45** empty (T), **1.05** found; `.S` **1.00** ×1 | ✅ verified | found, at the NUL, empty |
| `0xfecf02` | `strchk` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 3 rows + 1 `.S` | 9 / 134 both empty, 57 / 534 equal, 54 / 500 one byte differs | **1.98** both empty (T), **1.45** equal (T), **1.39** one byte differs (T); `.S` **1.00** ×1 | ✅ verified | equal, one byte differing, both empty (the compare's sign) |
| `0xfecf24` | `fmt_str` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 9 / 144 empty, 59 / 634 a name and an extension | **2.33** empty (T), **1.65** a name and an extension (T); `.S` **1.00** ×1 | ✅ verified | a name to its 8.3 form: a dotless name left unpadded, after 8 bytes the 9th skipped |
| `0xfecf58` | `unfmt_str` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 2 rows + 1 `.S` | 8 / 130 empty, 72 / 664 a padded name | **1.84** empty (T), **1.52** a padded name (T); `.S` **1.00** ×1 | ✅ verified | the 8.3 form back: an 8-byte form gets a bare dot |
| `0xfed070` | `merge_str` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 5 rows + 1 `.S` | 9 / 262 empty .. 830 / 10418 the desk's info line | **1.43** empty (T), **1.41** no codes (T), **0.50** the desk's info line, **0.85** a string, **1.45** a lone %S (T); `.S` **1.00** ×1 | ✅ verified | %L (signed, through ldiv), %W (a slot's FIRST word), %S, %%; 4-byte slots, the offset sign-extended at slot 8193; $80000000 prints "0"; a trailing % reads past the NUL; the desk's own info line; its two `jsr`s to lmul/ldiv relocated into the pinned region |
| `0xfed12e` | `wildcmp` (`src/aes/strings.c`, ships `src/aes/optimize.S`) | 4 rows + 1 `.S` | 15 / 194 a literal pattern, the first byte differs .. 133 / 1308 *.* against a name | **1.28** both empty (T), **1.01** *.* against a name, **0.86** one byte off, **1.34** a literal pattern, the first byte differs (T); `.S` **1.00** ×1 | ✅ verified | *, ?, a literal pattern, both empty, one byte off |
| `0xfe3db4` | `lmul` (Alcyon's runtime, `src/aes/strings.c`, ships `optimize.S`'s second region) | 1 row + 1 `.S` | 25 / 458 a negative factor | **0.78** a negative factor; `.S` **1.00** ×1 | ✅ verified | signed 32x32 through three `mulu`s, every sign; transcribed only so merge_str's `jsr` lands in a pinned region (its C is under the bar) |
| `0xfe3e08` | `ldiv` (Alcyon's runtime, `src/aes/strings.c`, ships `optimize.S`'s second region) | 5 rows + 1 `.S` | 29 / 530 a small dividend: one divu.w .. 348 / 3030 a large dividend: bit by bit | **0.76** a small dividend: one divu.w, **0.55** a large dividend: bit by bit, **0.75** a negative dividend, **1.43** 368640 / 4608: $fedf86's divide by a track (T), **2.59** 100000 / 30000: $fe667a's x*100 over a word (T); `.S` **1.00** ×1 | ✅ verified | quotient in D0, remainder at $8c3e: one `divu.w`, bit by bit, every sign; $80000000 dividend answers 0 remainder $80000000; both negative leaves a POSITIVE remainder; /0 and small/$80000000 host refusals (vector 5). Its C is 1.43 on $fedf86's divide by a track and 2.59 on $fe667a's x*100 over a word — its real callers' shapes — so it ships as `.S` |
| `0xfecca6` | `r_get` (`src/aes/rect.c`, ships `src/aes/optimize.S`) | 1 row + 2 `.S` + 1 Line-F | 9 / 212 the desktop window | **1.17** the desktop window (T); `.S` **1.00** ×2 | ✅ verified | each word stored before the next is read (x laid over rect.y reads back); five pointers on the bus |
| `0xfeccbe` | `r_set` (`src/aes/rect.c`, ships `src/aes/optimize.S`) | 1 row + 2 `.S` + 1 Line-F | 4 / 120 the desktop's words | **1.77** the desktop's words (T); `.S` **1.00** ×2 | ✅ verified | its four frame words stored as two longwords; mixed-sign words |
| `0xfeccca` | `rc_copy` (`src/aes/rect.c`, ships `src/aes/optimize.S`) | 1 row + 2 `.S` + 1 Line-F | 5 / 128 an object's rectangle | **1.36** an object's rectangle (T); `.S` **1.00** ×2 | ✅ verified | two longwords in turn: to = from+4 copies the first twice; downward overlap |
| `0xfeccd6` | `inside` (`src/aes/rect.c`, ships as C) | 6 rows + 1 Line-F | 8 / 128 left of it .. 18 / 234 the origin | **0.91** the origin, **1.00** left of it, **0.91** the last row, **0.93** the far edge down, **0.91** the desktop's middle, **1.07** the menu bar, above the desktop | ✅ verified | every edge on both sides, each axis's far-edge wrap separately, negatives, the desktop; the menu bar above the desktop (a point there, 1.07, its worst row) |
| `0xfecd0c` | `rc_equal` (`src/aes/rect.c`, ships `src/aes/optimize.S`) | 3 rows + 6 `.S` + 1 Line-F | 9 / 170 equal, 7 / 132 x differs, 9 / 164 h differs | **1.29** equal (T), **1.33** x differs (T), **1.34** h differs (T); `.S` **1.00** ×6 | ✅ verified | each word differing, equal, the snapshot's rectangles; leaves through the shared tails |
| `0xfecd8c` | `rc_union` (`src/aes/rect.c`, ships `src/aes/optimize.S`) | 9 rows + 9 `.S` + 1 Line-F | 27 / 316 a far edge that wraps .. 31 / 336 equal | **1.22** a far edge that wraps (T), **1.21** disjoint (T), **1.14** equal (T), **1.22** from inside into (T), **1.21** from to the lower right (T), **1.16** from to the upper left (T), **1.16** into inside from (T), **1.18** negative origins (T), **1.14** the desktop window (T); `.S` **1.00** ×9 | ✅ verified | every min/max branch, wrap, the y pass reading the x pass's stores (overlap), the desktop |
| `0xfecde4` | `rc_constrain` (`src/aes/rect.c`, ships `src/aes/optimize.S`) | 8 rows + 8 `.S` + 1 Line-F | 19 / 244 a far edge that wraps .. 25 / 300 wider and taller than its container | **1.22** a far edge that wraps (T), **1.22** already inside (T), **1.11** off to the lower right (T), **1.24** off to the upper left (T), **1.22** touching the far edges (T), **1.24** touching the near edges (T), **1.14** wider and taller than its container (T), **1.22** an object to the desktop (T); `.S` **1.00** ×8 | ✅ verified | pull-up/pull-back on each axis, wider than its container, the container's extent read AFTER the origin store (overlap), near and far edge ties, an object to the desktop |
| `0xfdaf20` | `hex_dig` (`src/aes/infscan.c`) | 3 rows + 1 Line-F | 33 / 398 'F', 29 / 364 '9', 30 / 376 'a' | **0.32** 'F', **0.24** '9', **0.27** 'a' | ✅ verified | the signed low byte, both sides of every range, lower case = 0, the high byte ignored |
| `0xfdaf5c` | `uhex_dig` (`src/aes/infscan.c`) | 3 rows + 1 Line-F | 28 / 356 9, 32 / 390 15, 30 / 372 16 | **0.20** 9, **0.28** 15, **0.24** 16 | ✅ verified | a signed word: 16, -1, $8000, $0105 |
| `0xfdaf92` | `scan_2` (`src/aes/infscan.c`) | 2 rows + 1 Line-F | 121 / 1442 the snapshot's #E field, 126 / 1478 the unset field | **0.24** the snapshot's #E field, **0.25** the unset field | ✅ verified | two UPPER-case hex digits — the snapshot's DESKTOP.INF #E field and a #M "FF" (-1: lower case reads 0, so only "FF" is the unset marker), the cursor += 3 with the separator skipped unread and its top byte kept, the answer word over its own text |
| `0xfdafca` | `save_2` (`src/aes/infscan.c`) | 2 rows + 1 Line-F | 115 / 1464 the #E field written back, 119 / 1498 letter digits | **0.14** the #E field written back, **0.14** letter digits | ✅ verified | the low byte's two digits + ' ', #E written back, the top byte kept |
| `0xfecf84` | `fs_sset` (the TEXT SET; the map has get/set reversed, `src/aes/objtext.c`, C; lstcpy's `.S` through glue) | 1 row + 1 Line-F | 73 / 868 the selector's path | **0.97** the selector's path (T→) | ✅ verified | *ptext := te_ptext FIRST, then lstcpy(te_ptext re-read, text) (overlap into the TEDINFO), then *txtlen := te_txtlen read AFTER the copy (a copy over the length); every pointer, ob_spec and te_ptext tagged |
| `0xfecfb2` | `inf_sset` (`src/aes/objtext.c`) | 1 row + 1 Line-F | 94 / 1174 the selector's selection | **0.55** the selector's selection (T→) | ✅ verified | Alcyon: its answers go into its own frame's locals (the stack band) — the C does the copy only |
| `0xfecfd6` | `fs_sget` (the TEXT GET, `src/aes/objtext.c`) | 1 row + 1 Line-F | 147 / 1466 the selector's path | **0.93** the selector's path (T→) | ✅ verified | lstcpy(text, te_ptext) over the selector's path, selection and a row; the bus |
| `0xfecfee` | `inf_fldset` (`src/aes/objtext.c`) | 2 rows + 1 Line-F | 15 / 244 set, 14 / 236 clear | **0.79** set, **0.78** clear | ✅ verified | a state word set/cleared from a flag, and the high byte's bit; seven C arguments, priced entered lower (the kit's lowered-sp pricing) |
| `0xfed010` | `inf_gindex` (`src/aes/objtext.c`) | 2 rows + 1 Line-F | 49 / 642 none of nine rows, 16 / 236 the first row | **0.96** none of nine rows, **0.97** the first row | ✅ verified | the first SELECTED (low byte bit 0 only) of count objects, -1 none: nine rows none/first/middle/last, count 1, COUNT 0 WALKS 65,536 OBJECTS (a `dbf`), the signed index (an object below the tree) |
| `0xfed03a` | `inf_what` (`src/aes/objtext.c`) | 4 rows + 1 Line-F | 40 / 550 neither .. 53 / 710 Cancel | **0.38** Cancel, **0.38** OK, **0.38** both, **0.30** neither | ✅ verified | neither/OK/Cancel/both; `cancel` is NEVER READ (0, and OK itself); the found index added into its own caller's frame word before that object's state is cleared; its body ends in the shared tails |
| `0xfed19e` | `ob_sst` (`src/aes/oblib.c`) | 4 rows + 1 Line-F | 63 / 922 a string .. 71 / 992 OK, a button | **0.79** OK, a button, **0.74** a formatted text row, **0.75** the root, a box, **0.77** a string | ✅ verified | every selector object; staged G_TEXT/G_FTEXT/G_FBOXTEXT/G_BOXTEXT/G_TITLE/G_IMAGE/G_IBOX, types 19/33, a high byte over G_BOX, a negative spec, border $80; EXIT and DEFAULT buttons; the thickness wrapping at 129 (128 stays, $8000, -1); INDIRECT follows ob_spec RE-READ from the object; the type, spec and flags READ BACK through the caller's pointers (the answer too); all eight pointers on the bus. Nine C arguments: priced with our side's stack pointer lowered by the 12 bytes that do not fit the kit's argument area |
| `0xfed27c` | `everyobj` (`src/aes/oblib.c`) | 2 rows + 1 Line-F | 2042 / 22478 the file selector from its root, 94 / 1198 a leaf alone | **0.71** the file selector from its root, **0.69** a leaf alone | ✅ verified | the whole selector at max_depth 8/2/1/0, subtrees stopping on `last`, HIDETREE, routines that HIDE and PRUNE (ob_flags and ob_head re-read after each call), word-wrapping positions, the deepest chain that fits (seven), a descent onto `last` at the eighth level and a climb to the root's level that both end without a halt, the ROM's everyobj into the ROM's mkrect against the C pair in VISITING ORDER; the routine gets the TAGGED tree. Its routine is an Alcyon call (`staged_call.h`'s `call_alcyon_object`: the 10-byte frame and `jsr (a0)` on target, really exercised at Tier 3 — swapping its x/y pushes reds both rows). A LEVEL OUTSIDE THE FRAME ARRAYS HALTS ON BOTH BUILDS (eight deep; a climb above `first`'s level) — a divergence, see "Not reconstructed". Eight C arguments, priced entered lower |
| `0xfe5a62` | `or_start` (`src/aes/rlist.c`) | 1 row + 1 Line-F | 1065 / 18110 the snapshot's pool | **0.24** the snapshot's pool | ✅ verified | the whole pool threaded, ORECT 79 on top, a window's list head untouched; a stale head (the `clr.l` ends the list); ROM finding: the desktop's ORECT is left on both the free list and window 0's list. Runs poisoned |
| `0xfe5aac` | `get_orect` (`src/aes/rlist.c`) | 2 rows + 1 Line-F | 18 / 300 the snapshot's head, 16 / 254 an empty list | **0.39** the snapshot's head, **0.34** an empty list | ✅ verified | the head unlinked; the last one; an empty list answers 0 and stores nothing; a tagged head answered as stored, its link read through 24 bits; stale free pool |
| `0xfe5acc` | `mkpiece` (`src/aes/rlist.c`, min/max's `.S` through glue) | 5 rows + 1 Line-F | 114 / 1502 side 4 of the desktop .. 124 / 1614 side 3 of the desktop | **0.75** side 0 of the desktop (T→), **0.78** side 1 of the desktop (T→), **0.77** side 2 of the desktop (T→), **0.73** side 3 of the desktop (T→), **0.74** side 4 of the desktop (T→) | ✅ verified | every side and the default; word far edges wrapped and compared signed; ORDER overlaps — the free head IS the rectangle and IS the cut; an EXHAUSTED POOL builds its piece at $0 (no check: a bus error on the machine); pointers tagged, the link stored as handed in; a cut pointer at $fffffffc whose words wrap to $0..$7 |
| `0xfe5ba8` | `brkrct` (`src/aes/rlist.c`) | 5 rows + 1 Line-F | 28 / 440 a cut right of it .. 643 / 8080 4 pieces of the desktop | **0.58** a cut right of it (T→), **0.83** a cut above it (T→), **0.75** 0 pieces of the desktop (T→), **0.79** 1 pieces of the desktop (T→), **0.79** 4 pieces of the desktop (T→) | ✅ verified | all 16 piece subsets against a tiling model; every `ble` of the overlap test on touching edges; a cut equal to the rectangle; signed compare of wrapped edges; all four flags decided before the first piece — after or_start the rectangle is its own first piece (real data); exhaustion mid-split answers 0 for a cut it made; every pointer tagged |
| `0xfe5c9a` | `mkrect` (`src/aes/rlist.c`) | 4 rows | 32 / 486 a window with no list .. 1400 / 17392 a list of four, cut again | **0.77** the desktop in four (T→), **0.57** a cut that misses (T→), **0.49** a window with no list (T→), **0.76** a list of four, cut again (T→) | ✅ verified | the desktop's list cut in four and marked WIN_BROKEN; a miss; a list of four (its own first cut, chained) cut again; the signed window index (window -1's record below the table); an exhausted pool loses the last pieces and is NOT marked broken; the tree never read. No Line-F door: reached only by everyobj's `jsr (a0)` on the address newrect pushes ($fe5d68) — a ROM address used as a value, owed by `src/aes/wrect.c` (census kind CODE) |
| `0xfea0a8` | `ob_find` (opcode 43's, `src/aes/objects.c`, r_set/inside's `.S` through glue) | 7 rows + 1 Line-F | 158 / 2140 outside the root .. 3072 / 37466 a file line, two levels | **0.74** outside the root (T→), **0.58** a file line, two levels (T→), **0.57** the first child, past ten siblings (T→), **0.57** the root, every child missed (T→), **0.59** the slider, three levels (T→), **0.72** depth 0, the root only (T→), **0.51** from the slider's track, its parents summed (T→) | ✅ verified | a descent to the LAST child, the depth limit (0, 1, 2, -1 = every level), steps back across the root's eleven children by get_prev, a non-root start (origin = ob_actxywh of its parent), every edge of inside; HIDETREE on an object/its parent/the root; overlapping siblings; wrapping sums; the tree on the bus; its two frame GRECTs a host slot (AES_OB_FIND_RECTS). THE STEP BACK ONLY WHEN dosibs && lastfound != -1 ($fea17c/$fea182): a start at object -1 that hits and then misses ends the search (the review's divergence, fixed and pinned; the model fixed with it) |
| `0xfea1ba` | `ob_add` (40, `src/aes/objects.c`) | 3 rows + 1 Line-F | 50 / 684 a file line added to a leaf, 48 / 668 to the box of nine, 25 / 414 no parent | **0.52** a file line added to a leaf, **0.57** to the box of nine, **0.19** no parent | ✅ verified | as the last child, to a leaf (head), the child already the tail (its next stored twice), either -1 |
| `0xfea21e` | `ob_delete` (41, `src/aes/objects.c`) | 4 rows + 1 Line-F | 25 / 408 the root .. 254 / 3108 the tail of 11 | **0.49** the tail of 11, **0.62** the head of 11, **0.56** an only child, **0.10** the root | ✅ verified | head/tail/middle of 11 and of 9, an only child (head and tail -1), the root untouched, its own next kept; poisoned but for its link longwords (`LINKS_UNPOISONED`, measured per case) |
| `0xfea2be` | `ob_order` (45, `src/aes/objects.c`) | 4 rows + 1 Line-F | 25 / 408 the root .. 507 / 6550 a middle one after the last by count | **0.62** the first of 11 to the tail, **0.55** a middle one after the last by count, **0.48** the tail to the head, **0.27** the root | ✅ verified | 0/-1/1/3/8/-2, head↔tail, the head back to the head (reads the head after the unlink); ROM DEFECTS pinned: an only child to 0 leaves no tail, to -1 WRITES THE WORD 24 BYTES BELOW THE TREE (the file selector's RSH_NTED), past the end links it among the parent's own siblings |
| `0xfea5dc` | `get_prev` (`src/aes/objects.c`) | 2 rows + 1 Line-F | 131 / 1510 the tail of 11, 31 / 484 the head | **0.55** the tail of 11, **0.36** the head | ✅ verified | -1 for the head, the second, the tail of 11 |
| `0xfea4b6` | `ob_fs` (`src/aes/objects.c`) | 1 row + 1 Line-F | 25 / 410 the OK button | **0.41** the OK button | ✅ verified | flags stored, state answered; the flags word over the state answers the flags |
| `0xfea4e8` | `ob_actxywh` (`src/aes/objects.c`) | 2 rows + 1 Line-F | 399 / 5188 the slider, four levels, 337 / 4332 the first of eleven siblings | **0.35** the slider, four levels, **0.47** the first of eleven siblings | ✅ verified | the screen GRECT; w then h after ob_offset's stores (a GRECT laid from ob_y) |
| `0xfea538` | `ob_relxywh` (`src/aes/objects.c`) | 1 row + 1 Line-F | 50 / 674 a file line | **0.68** a file line (T→) | ✅ verified | wcopy out: the forward smear one word above/below |
| `0xfea55e` | `ob_setxywh` (`src/aes/objects.c`) | 1 row + 1 Line-F | 50 / 674 a file line | **0.67** a file line (T→) | ✅ verified | wcopy in: the forward smear one word above/below |
| `0xfe92ae` | `ob_center` (54, form_center, `src/aes/objects.c`) | 3 rows + 1 Line-F | 82 / 1512 the file selector, 71 / 1446 the menu tree, not outlined, 82 / 1512 a negative half, truncated toward zero | **0.76** the file selector (T→), **0.75** the menu tree, not outlined (T→), **0.76** a negative half, truncated toward zero (T→) | ✅ verified | outlined (the selector, an alert) and not (the menu tree); `divs` toward zero on both halves and the cell (odd negative, negative cell), min(x,3) both arms, a wide screen, the answer over the root's own rect, tagged; ROM finding: it tests OUTLINED (bit 4), not SHADOWED; a zero cell width a host refusal (vector 5) |
| `0xfea622` | `fix_chpos` (`src/aes/resource.c`) | 2 rows | 39 / 564 x-like, cells times the cell, a negative offset, 32 / 468 full width | **0.51** x-like, cells times the cell, a negative offset, **0.55** full width | ✅ verified | cells x gl_wchar/gl_hchar, an x/width of 80 = gl_width; ROM finding: the offset byte signed only ABOVE 128 (`cmpi.w #128; ble`: offsets -127..128); the flag any nonzero; the `muls` low word; the bus |
| `0xfea69c` | `rs_obfix` (114, `src/aes/resource.c`) | 1 row | 278 / 3420 a desk object | **0.28** a desk object | ✅ verified | the desk's objects as the ROM holds them (cells) at five indices; the signed index; ORDER through gl_wchar; D0 = 1 |
| `0xfea716` | `get_sub` (`src/aes/resource.c`) | 1 row | 23 / 360 an element | **0.57** an element | ✅ verified | every section; signed `muls`; the unsigned offset word; the signed section (-1 reads below the header); the tagged header kept |
| `0xfea742` | `get_addr` (rsrc_gaddr's switch, table $fefbf8, `src/aes/resource.c`) | 4 rows + 1 Line-F | 32 / 480 past the last type .. 128 / 1684 a TEDINFO's field | **0.64** a tree, **0.25** a TEDINFO's field, **0.37** a free string, **0.54** past the last type | ✅ verified | all 17 types over both ROM resources; R_TREE stores AES_RS_INDEX and re-reads it `movea.w` (a tree >= $2000 reads BELOW the table); 17/$7fff/$8000/$ffff answer -1 (unsigned); a read across the bus top refused by name |
| `0xfeaa0a` | `fix_long` (`src/aes/resource.c`) | 1 row | 31 / 418 an offset | **0.35** an offset | ✅ verified | -1 left, -2/0 fixed; the bus and a tagged header; the slot over rs_hdr |
| `0xfea9f8` | `fix_ptr` (`src/aes/resource.c`) | 1 row | 197 / 2560 a template | **0.26** a template | ✅ verified | a fresh TEDINFO template to the snapshot's value |
| `0xfea9d4` | `fix_nptrs` (`src/aes/resource.c`) | 1 row | 4104 / 52172 the AES's 30 free strings | **0.26** the AES's 30 free strings | ✅ verified | the fresh AES copy's 30 free strings = the snapshot's bytes; the last 0/-1/-$8000 (signed) |
| `0xfea86a` | `fix_trindex` (`src/aes/resource.c`) | 2 rows | 228 / 2726 the AES's resource as the ROM holds it, 811 / 9260 the desk's resource as the ROM holds it | **0.22** the AES's resource as the ROM holds it, **0.20** the desk's resource as the ROM holds it | ✅ verified | fresh AES and desk copies = the snapshot's table and global[5..6]; ORDER: the global over the header's ntree (the count read after the store) |
| `0xfea8bc` | `fix_objects` (`src/aes/resource.c`) | 2 rows | 16224 / 198812 the AES's resource as the ROM holds it, 74368 / 912158 the desk's resource as the ROM holds it | **0.19** the AES's resource as the ROM holds it, **0.19** the desk's resource as the ROM holds it | ✅ verified | fresh 38 + 172 objects = the snapshot's EXACTLY but the 17 bytes edited since (named per group); G_BOX/G_IBOX/G_BOXCHAR keep their colours, the extended type masked, a spec of -1 left; D0 |
| `0xfea918` | `fix_tedinfo` (`src/aes/resource.c`) | 2 rows | 11097 / 134208 the AES's resource as the ROM holds it, 22551 / 271794 the desk's resource as the ROM holds it | **0.18** the AES's resource as the ROM holds it (T→), **0.18** the desk's resource as the ROM holds it (T→) | ✅ verified | fresh 13 + 26 TEDINFOs = the snapshot; lengths strlen+1 THROUGH the pointer just stored; -1 text/template/both keep their length; ORDER: a TEDINFO over the header (text fixed before the template) |
| `0xfeaba4` | `do_rsfix` (`src/aes/resource.c`) | 3 rows + 1 Line-F | 18686 / 230390 the AES's resource as the ROM holds it, 26915 / 326140 the desk's resource as the ROM holds it, 3806 / 47548 an application's resource, icons and all | **0.14** the AES's resource as the ROM holds it (T→), **0.17** the desk's resource as the ROM holds it (T→), **0.12** an application's resource, icons and all (T→) | ✅ verified | header/length into global[7..9]; every section incl. ICONBLKs (a built resource — neither ROM resource has one), BITBLKs, strings, images, empty sections; counts from rs_hdr, not the argument |
| `0xfeaa38` | `rs_sglobal` (`src/aes/resource.c`) | 1 row | 17 / 292 the desk's | **0.48** the desk's | ✅ verified | AES/desk/tagged; ORDER: global[7..8] laid over AES_RS_GLOBAL |
| `0xfeaa86` | `rs_gaddr` (112, `src/aes/resource.c`) | 2 rows | 195 / 2606 a TEDINFO's field, 109 / 1526 a tree | **0.27** a TEDINFO's field, **0.44** a tree | ✅ verified | all 17 types + two out of range; the answer over rs_hdr (read back); the slot pointer held once, as the ROM holds A5 |
| `0xfeaab2` | `rs_saddr` (113, `src/aes/resource.c`) | 1 row | 195 / 2602 an ob_spec | **0.25** an ob_spec | ✅ verified | the store at R_OBSPEC; a type naming no address touches no bus; a tree-table entry at the bus top refused by name (odd: the address error; even: past the top) — the host-bound hole the review found |
| `0xfeac4e` | `rs_fixit` (`src/aes/resource.c`) | 2 rows | 16277 / 199544 the AES's resource as the ROM holds it, 74421 / 912890 the desk's resource as the ROM holds it | **0.19** the AES's resource as the ROM holds it, **0.19** the desk's resource as the ROM holds it | ✅ verified | chained after do_rsfix: the whole resource and global[] = the snapshot |
| `0xfea6e6` | `rs_str` (`src/aes/resource.c`) | 2 rows | 695 / 6974 the longest alert, 194 / 2636 an empty string | **0.70** the longest alert (T→), **0.19** an empty string (T→) | ✅ verified | all 30 free strings (3 empty, alerts to 167 B); string 30, past the last (frimg[0]) |
| `0xfeac80` | `sc_read` (80, `src/aes/shell_buf.c`) | 1 row | 66 / 740 a path | **0.78** a path (T→) | ✅ verified | three paths, not a byte past the NUL; the tagged pointer; D0 = lstcpy's count |
| `0xfeac94` | `sc_write` (81, `src/aes/shell_buf.c`) | 1 row | 360 / 3288 a long path | **0.95** a long path (T→) | ✅ verified | three paths incl. empty and long; D0 = lstcpy's count |
| `0xfeaca8` | `sh_read` (120, `src/aes/shell_buf.c`) | 1 row | 834 / 8020 both lines | **0.99** both lines (T→) | ✅ verified | both 128-byte lines, not 129; both pointers tagged; the tail buffer over the shell's own line |
| `0xfeacd4` | `sh_write` (121, `src/aes/shell_buf.c`) | 1 row | 835 / 7578 both lines | **1.00** both lines (T→) | ✅ verified | both lines in; doexec stored, ISDEF/DODEF cleared, isgem as a flag ($0100 -> 1), `isover` unread; the stored pointers tagged |
| `0xfead26` | `sh_get` (122, `src/aes/shell_buf.c`) | 1 row | 808 / 7690 a whole buffer | **0.98** a whole buffer (T→) | ✅ verified | 0/1/80/255/256 bytes of the DESKTOP.INF buffer; the bus |
| `0xfead40` | `sh_put` (123, `src/aes/shell_buf.c`) | 1 row | 805 / 7160 a whole buffer | **0.98** a whole buffer (T→) | ✅ verified | 0/1/80/255/256 bytes into the DESKTOP.INF buffer; the bus |
| `0xfee5c8` | `rom_ram` (`src/aes/resource.c`) | 9 rows | 43 / 660 past the last part .. 101491 / 1240844 the desk's first, replayed | **0.98** the default DESKTOP.INF (T→), **0.99** the desk's icons, three buffers (T→), **0.99** the rest of the desk's icons (T→), **0.45** past the last part (T→), **0.90** the AES's again (T→), **0.37** the desk's again, the desktop sized (T→), **0.19** the format dialogs' first (T→), **0.19** the desk's first, replayed (T→), **0.14** the AES's first, replayed (T→) | ✅ verified | every part: 3 DESKTOP.INF, 2/4 the desk's icons, 6/7/$7fff answer the entry address, a part < 0 is the AES's re-request; the format dialogs' first request is the snapshot's own next move (its flag 1), the desk's and the AES's first requests REPLAYED over fresh copies = the snapshot; the desk's re-request sizes the desktop through the desk's OWN global[] $96ba; the kept global[]s staged FILL (the review's three survivors killed); dsptch with AES_INDISP clear a host halt |
| `0xfeaa58` | `rs_free` (111, `src/aes/resource.c`, through `dos_free`) | 1 row | 57 / 844 the desk's | **0.79** the desk's | ✅ verified | Mfree(global[7..8]) over the staged recording trap, the whole ordered ledger; both returns parked; DOS_AX the word, DOS_ERR the LONG's sign ($00008000, EIMBA, $80000000); rs_hdr untouched |
| `0xfee4de` | `rom_rsc_init` (gem_entry's `jsr`, `src/aes/resource.c`, through `dos_alloc`) | 1 row | 51862 / 450030 the snapshot's own block | **1.00** the snapshot's own block (T→) | ✅ verified | Malloc answered with the snapshot's own block $cc72: the bundle copied byte for byte over a FILL-staged block, the six-part table (stale-staged) = the snapshot's; ROM findings: the Malloc is NOT checked, and the AES part's length runs 5 bytes into the desk's resource (a word count subtracted from a byte offset) |
| `0xfe3bba` | `dos_alloc` (`src/aes/gemdosif.c`) | 3 rows | 23 / 336 an odd size, an odd block, 21 / 324 even, 20 / 322 no memory | **0.94** an odd size, an odd block, **0.98** even, **1.10** no memory | ✅ verified | direct and through Line-F over the recording trap: the size and the block each rounded up to even (a longword sum: $ffffffff asks for 0), the FAILURE ARM (DOS_ERR := 1, answer 0) pinned directly; ROM finding: a success does NOT clear DOS_ERR. "No memory" is AT THE BAR (1.0993): the C's DOS_ERR store is image-relative ($98ec is past a d16), 46 cycles against the ROM's absolute `move.w #1,$98ec`'s 20 |
| `0xfe3c26` | `dos_free` (`src/aes/gemdosif.c`) | 8 direct/Line-F | — | unpriced — a HOST ARGUMENT (its caller's return site, which no frame carries; the gemdos_call precedent); priced inside rs_free's row | ⚠️ verified, unpriced | through `__DOS` ($fe3c28/$fe39b6/$fe3c3e): both returns parked (direct = the sentinel, Line-F = the stub's word after the call), DOS_AX the answer's word, DOS_ERR the LONG's sign: EIMBA, odd, $8000 word, tagged |
| `0xfecb5a` | `gsx2` (`src/aes/gsx.c`, ships `src/aes/gsx.S`) | 1 row + 1 Line-F + 2 `.S` | 124 / 2158 vsl_color 3, contrl staged | **1.20** vsl_color 3, contrl staged (T, own); `.S` **1.00** ×2 | ✅ verified | THE BRIDGE (`include/aes/gsx.h`): the host checks both hops of the AES's one `trap #2` — vector `$88` and SYSVAR_VDI_ENTRY `$8c2a` → `$fc4ebc` — and halts by name on either, then runs the VDI's C twin of its entry over pb `$9466` with the VDI's C cores bound per case (28 functions); the target build makes the real trap (D0 = `$73`, D1 = `$9466`). pb[0] := `$c7e0` stored over a stale value; the VDI's unknown-handle arm through the AES; a bare-gsx2 polyline. Own 1.20 (T), whole 1.01 |
| `0xfe87d2` | `gsx_ncode` (`src/aes/gsx.c`, ships `src/aes/gsx.S`) | 2 rows + 1 Line-F + 2 `.S` | 142 / 2464 vqt_attributes, 2770 / 32612 v_gtext, three characters | **1.27** vqt_attributes (T), **1.27** v_gtext, three characters (T); `.S` **1.00** ×2 | ✅ verified | four frame-built calls (vqt_attributes, vq_mouse, vsl_udsty, v_gtext of three characters); contrl[0,1] stored as one longword, then [3], gl_handle (`$c766`) read after them; handle 0; the counts are words (n_intin -1 → `$ffff`) |
| `0xfe87f0` | `gsx_1code` (`src/aes/gsx.c`, ships `src/aes/gsx.S`) | 1 row + 1 Line-F + 2 `.S` | 144 / 2374 vswr_mode 3 | **1.40** vswr_mode 3 (T); `.S` **1.00** ×2 | ✅ verified | nine one-word attribute calls end to end (vsl_type, vsl_color, vst_color, vsf_interior, vsf_style, vsf_color, vswr_mode, vsl_udsty, v_show_c); transcribed, and the `.S` is also gsx_mon's `bsr.w` target |
| `0xfe8a72` | `gsx_moff` (`src/aes/gsx.c`, ships as C: its hide path makes a Line-F call) | 2 rows + 1 Line-F | 5 / 102 the nest already open, 353 / 4686 the snapshot's cursor: v_hide_c | **1.23** the nest already open (accepted (A)), **0.95** the snapshot's cursor: v_hide_c (V, `glue`) | ✅ verified | the shown cursor: v_hide_c over the snapshot's drawn arrow (the screen restored, gl_mouse_shown `$9b6e` := 0, a PTSIN left elsewhere put back); the nest 1 / 2 / `$ffff` counted as a word (-1 → 0); moff then mon back to the snapshot's screen. The open nest is ACCEPTED at 1.23 (62 → 76 own cycles): the C's floor is the image pointer and `adda.l #$c86a` (above a d16), once the hide path was split into a `noinline` static so the counter path keeps no frame; no `.S` is possible, since the hide path's Line-F call word cannot be kept byte-exact. v_hide_c: 0.95 own, 1.12 with its 92 thunk cycles, so `glue` (T→G) |
| `0xfe8a8e` | `gsx_mon` (`src/aes/gsx.c`, ships `src/aes/gsx.S`) | 2 rows + 1 Line-F + 3 `.S` | 5 / 90 the nest still open, 1636 / 14932 the nest unwound: v_show_c | **2.00** the nest still open (T), **1.58** the nest unwound: v_show_c (T); `.S` **1.00** ×3 | ✅ verified | `sub.w` on the nest: 1 → 0 calls v_show_c(1), which redraws the arrow, and sets gl_mouse_shown; 2 → 1; 0 → `$ffff` shows nothing. intin[0] and the flag are staged stale, because the poison pass is vacuous on this arm (it inverts gl_moff and steers the ROM onto the counter path) |
| `0xfe8afa` | `v_pline` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 3385 / 31774 a triangle | **0.86** a triangle (V, `net`) | ✅ verified | a triangle (4 points, 3 segments); PTSIN at the caller's points for the call and put back after (`$fe8bd0`); a tagged pointer; the AES's own ptsin as the points. Own 0.86, 1.04 with its 92 thunk cycles, whole 1.00: the OS both run is 31,224 of the ROM's 31,774 cycles |
| `0xfe8b0e` | `vs_clip` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 215 / 3258 on, a rectangle | **0.82** on, a rectangle (V, `net`) | ✅ verified | clipping on and off; 0.99 with its thunks |
| `0xfe8b22` | `vst_height` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 243 / 3582 the large font's | **1.02** the large font's (V, `glue`) | ✅ verified | four answers, each read after the store before it (a chain through ptsout: every link); tagged pointers; a PTSIN left elsewhere is read, then put back (the wrapper never sets it); an odd pointer is a host address error. 1.02 own, 1.17 with its 92 thunk cycles, so `glue` (T→G) |
| `0xfe8b50` | `vr_recfl` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 4331 / 37928 a rectangle | **0.82** a rectangle (V, `net`) | ✅ verified | the MFDB pointer into contrl[7..8], where it persists; tagged points and MFDB; n_intin 1 (the VDI's vr_recfl reads no intin); 0.99 with its thunks |
| `0xfe8b60` | `vro_cpyfm` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 3292 / 28550 screen to screen | **0.84** screen to screen (V, `net`) | ✅ verified | screen to screen, screen to form (tagged MFDB pointers); 0.98 with its thunks |
| `0xfe8b72` | `vrt_cpyfm` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 1015 / 11512 a form onto the screen | **0.91** a form onto the screen (V, `net`) | ✅ verified | a one-plane form onto the screen in two colours (fg 2, bg 5); 1.05 with its thunks |
| `0xfe8b88` | `vrn_trnfm` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 195 / 3094 standard to device | **0.87** standard to device (V, `net`) | ✅ verified | a standard form to device form; 1.04 with its thunks |
| `0xfe8b92` | `vsl_width` (`src/aes/gsx.c`) | 1 row + 1 Line-F | 173 / 2850 3 | **0.90** 3 (V, `net`) | ✅ verified | ptsin (w, 0) for widths 1 and 3; a PTSIN left elsewhere is read, then put back; 1.08 with its thunks |
| `0xfda992` | `gsx_fix` (`src/aes/gsx.c`, ships `src/aes/gsx.S`) | 2 rows + 1 Line-F + 5 `.S` | 16 / 214 the screen, 15 / 204 an icon's form | **2.21** the screen (T), **2.02** an icon's form (T); `.S` **1.00** ×5 | ✅ verified | the screen MFDB from work_out (`$c892`) and gl_nplanes (`$c914`); forms (2/16, 40/200, `$1fff`, and `$2000`, whose width wraps to 0: `lsl.w #3` then `lsr.w #4` on one word); addresses whose low word is 0 (`$10000`) or whose top byte is set (`$5a000000`) are still forms — the `bne` tests the whole long; the MFDB laid over work_out and over gl_nplanes (each read after the store before it); a tagged MFDB; odd and bus-top MFDBs refused on the host |
| `0xfeae04` | `sh_name` (`src/aes/shell_find.c`) | 2 rows | 185 / 1804 a full path, 176 / 1738 a name alone, scanned whole | **0.94** a full path (T→), **0.95** a name alone, scanned whole (T→) | ✅ verified | the name past the last separator, a name with none; direct and through Line-F. The C's per-byte back-scan passes 1.10 only on names of about 100 bytes (a review probe, unregistered); GEMDOS names are 8.3 |
| `0xfeae36` | `sh_envrn` (`src/aes/shell_find.c`) | 2 rows | 343 / 3670 PATH= in the AES's own environment, 464 / 5232 HOME= in the AES's own environment | **1.02** PATH= in the AES's own environment (T→), **0.96** HOME= in the AES's own environment (T→) | ✅ verified | its 46-byte frame kept whole in a host slot in the ROM's layout, plus the caller's saved A6's top byte past it (0 on a 24-bit bus): a name up to 31 bytes is served (its terminator lands as a 0 on that byte), and so is a compare whose rewritten length lands a 0 there; a nonzero byte, or anything further, halts by name (32 bytes and over, empty, the 256 wrap); ROM-alone cases pin what the ROM does on both sides. ROM findings: byte 5 of its 50-byte environment copy becomes `;` (right only for the AES's own `PATH=\0` layout), and its match is not anchored to a string's start |
| `0xfeaf1e` | `sh_path` (`src/aes/shell_find.c`) | 1 row | 704 / 8198 element 1 of the AES's own | **0.65** element 1 of the AES's own (T→) | ✅ verified | each PATH element built in turn with the name; an EMPTY element tests its caller's D6. Every application path enters with the dispatcher's 1 (`$fe5da8` `moveq #1,d6`), which the C takes. DIVERGENCE narrowed to sh_main's own sh_find (`$feb27e`), whose inherited D6 no C sees; a ROM-only case pins it (D6 = `\` leaves out the `\`) |
| `0xfeafbe` | `sh_find` (`src/aes/shell_find.c`) | 3 rows | 2000 / 23694 not there: the root and PATH tried, 401 / 4746 found as given, 407 / 4860 found with sh_main's kind of routine, a logger | **0.72** not there: the root and PATH tried (T→), **0.91** found as given (T→), **0.91** found with sh_main's kind of routine, a logger (T→) | ✅ verified | over REAL GEMDOS on the staged RAM disk (the ROM's own AES and desk resources as files, an application resource in SUBDIR, a header-claims-nothing file, a file cut short) and the scripted trap for the error arms; the caller's routine by `call_alcyon_pointer` — a logger, and one that sets DOS_ERR (the re-read after it pinned); the logger row runs call_alcyon_pointer's target asm. Its 22-byte frame kept whole: a name part up to 22 bytes is served (its NUL on the saved A6's top byte), 23 and over halt by name. The routine's top byte is unreachable (callers pass 0 or `$feaddc`). ROM finding: its DTA (`$b89a`) IS rs_str's buffer, so sh_path's rs_str("PATH=") overwrites the last Fsfirst's DTA |
| `0xfe3a1c` | `dos_sfirst` (`src/aes/gemdosif.c`) | 2 rows | 49 / 684 EFILNF, 42 / 622 found | **1.03** EFILNF, **1.05** found | ✅ verified | Fsfirst over the scripted trap, whose ledger records every frame whole (10 bytes); DOS_AX / DOS_ERR from the answer; a tagged spec; direct and through Line-F. GEMDOS 1.02 answers EFILNF for every miss (no directory, no drive), so the error arm that is not retried and DOS_AX 3 are reachable only over the scripted trap, and are pinned there |
| `0xfe3a52` | `dos_open` (`src/aes/gemdosif.c`) | 2 rows | 45 / 658 a handle, 48 / 684 EFILNF | **1.05** a handle, **1.06** EFILNF | ✅ verified | the handle, or 0 with DOS_ERR; direct and through Line-F; a tagged name handed to GEMDOS as pushed (the dispatcher's device-name test reads it through the bus) |
| `0xfe3a78` | `dos_read` (`src/aes/gemdosif.c`) | 1 row | 49 / 716 a header | **1.06** a header | ✅ verified | Fread's buffer longword recorded whole in the frame; a tagged buffer |
| `0xfe3a9a` | `dos_lseek` (`src/aes/gemdosif.c`) | 1 row | 43 / 674 to the start | **1.08** to the start | ✅ verified | Fseek's handle and mode passed as one longword (the ROM glue's own `move.l`) |
| `0xfe3c06` | `dos_sdta` (`src/aes/gemdosif.c`) | 4 direct/Line-F | — | unpriced — a HOST ARGUMENT (its caller's return site, parked through `$fe3c28`; the dos_free precedent) | ⚠️ verified, unpriced | Fsetdta over the scripted trap; through real GEMDOS it answers the dispatcher's own D0 (`$00fd0001` on the ROM, 0 on the host binding), which the next Fsfirst overwrites before anything reads DOS_AX/DOS_ERR |
| `0xfe3c0a` | `dos_close` (`src/aes/gemdosif.c`) | 4 direct/Line-F | — | unpriced — a HOST ARGUMENT (as dos_sdta) | ⚠️ verified, unpriced | Fclose over the scripted trap, both returns parked |
| `0xfeaae2` | `rs_readit` (`src/aes/resource.c`) | 2 rows | 664 / 8200 the header's read fails, 27766 / 336892 the desk's resource, whole | **0.88** the header's read fails (T→), **0.19** the desk's resource, whole (T→) | ✅ verified | over real GEMDOS and the scripted trap: open, header, Malloc, read, relocate; a tagged global and name. The worst row is a failed load (the C about the ROM on glue and walk; a whole load adds the relocation at about 5x). ROM findings: it closes handle 0 after a failed Fopen, stores dos_alloc's 0 into rs_hdr before testing it, ignores Fseek's answer; Malloc(0) returns a block in this GEMDOS (an rsh_rssize-0 file "loads") |
| `0xfeac5c` | `rs_load` (`src/aes/resource.c`) | 2 rows | 703 / 8700 the header's read fails, 102238 / 1250402 the desk's resource, whole | **0.85** the header's read fails (T→), **0.19** the desk's resource, whole (T→) | ✅ verified | as rs_readit, through sh_find's PATH walk. ROM finding: the walk's rs_str makes the AES's OWN resource current, so a failed rsrc_load leaves rs_global/rs_hdr the AES's |
| `0xfeb4be` | `w_getxptr` (`src/aes/wrect.c`) | 5 rows + 1 Line-F | 35 / 482 every row | **0.32** WS 0 of the desktop, **0.34** WS 1 of the desktop, **0.26** WS 2 of the desktop, **0.33** WS 3 of the desktop, **0.35** WS 4 of the desktop | ✅ verified | every arm of the five-row switch (`$fefcca`: 0 WS_FULL rec+16, 1 WS_CURR and 4 WS_TRUE the window tree's ob_x at `$9734` + wh*24 + 16, 2 WS_PREV rec+32, 3 WS_WORK rec+24) for the desktop, the last window and window -1 (signed `muls.w`: record and tree object below their tables); past 4 compared UNSIGNED (5, -1, `$7fff`): the ROM answers D0 as the switch left it — `which` in the low word, pinned; the caller's high word unpinned (no caller passes one). A core over words alone |
| `0xfeb53e` | `w_getsize` (`src/aes/wrect.c`, rc_copy's `.S` through glue) | 5 rows + 1 Line-F | 92 / 1248 WS 0 .. 98 / 1318 WS 4 | **0.36** WS 0 of the desktop (T→), **0.36** WS 1 of the desktop (T→), **0.34** WS 2 of the desktop (T→), **0.36** WS 3 of the desktop (T→), **0.50** WS 4 of the desktop (T→) | ✅ verified | each rectangle copied; WS_TRUE grown by 2 only when w AND h, READ BACK from the copy, are non-zero (no width / no height / empty / 1×1); the word wrap (`$ffff` → 1, `$7fff` → `$8001`); ORDER overlaps — the answer a word and a longword over its source, below it; a tagged answer; window -1 |
| `0xfe5cee` | `newrect` (`src/aes/wrect.c`, rc_copy's `.S` through glue) | 5 rows | 141 / 1970 a closed window .. 2010 / 25146 a window over the desktop already cut in four | **0.72** a window over the desktop already cut in four (T→), **0.67** a window over the desktop (T→), **0.49** the desktop alone (T→), **0.34** a closed window (T→), **0.50** the desktop, its list of four (T→) | ✅ verified | the snapshot's desktop rebuilt from its own ORECT; a window over it cutting it; three windows (the top one cuts both below, a lower one leaves the upper); a list of four freed whole in list order; tagged links; closed windows and no-area windows stop before the walk (gl_mkrect's stale link left); the area read from gl_mkrect after the border grows it (`$fffe` wide and high: the list freed, no cut); an EXHAUSTED POOL builds the list at `$0`; window -1; the tree argument is the walk's alone. Since band 3 wave 1 the target hands everyobj mkrect's ALCYON ENTRY (`src/aes/wmupdate.S`, through `wrect.c`'s mkrect_routine), so our side runs its own mkrect's C: the two cut rows re-priced 0.81 → 0.67 and 0.89 → 0.72 (before, our side ran the ROM's mkrect, its cost hidden as ours). These rows are not (V), so they alone cannot see a target that hands the ROM's mkrect again: that pin lives on draw_change's and wm_*'s (V) rows, which REFUSE our cycles inside the AES's own spans. No Line-F door: everyobj's `jsr (a0)` on the address `$fec146` pushes — the door case is the ROM's own everyobj over the whole window tree against the C pair, newrect and mkrect bound through one hook. Hands everyobj mkrect BY ITS ROM ADDRESS on the host (`test_aes_rom_data.py`, CODE) |
| `0xfe8768` | `gr_mkstate` (`src/aes/gsxif.c`) | 1 row + 1 Line-F | 25 / 280 four answers | **1.00** four answers | ✅ verified | xrat, yrat, the buttons and the keyboard's shift state (`$c72a`) through the ROM's pc-relative table of their addresses (`$fe8780`); every link of the read-after-store chain (x over &yrat, y over &button, button over &kstate, all four one word); every answer pointer tagged; an odd one a host address error. Its C beats the table loop, so it ships as C |
| `0xfe8790` | `gsx_malloc` (`src/aes/gsxif.c`, through `dos_alloc`) | 1 row + 1 Line-F | 67 / 926 the snapshot's block | **0.98** the snapshot's block (T→) | ✅ verified | over the recording trap: the ledger `[(Malloc, $3400)]`; gl_tmp = the screen's MFDB with the snapshot's own block; an odd block rounded; no memory (DOS_ERR 1, fd_addr 0). ROM finding: the buffer is `$3400` = 13,312 bytes, never checked against a drop-down's size |
| `0xfe87b0` | `gsx_mfree` (`src/aes/gsxif.c`, through `dos_free`) | 1 row + 1 Line-F | 41 / 620 freed | **0.92** freed | ✅ verified | freed and EIMBA; the ledger `[(Mfree, gl_tmp's buffer)]`; both returns parked (`$fe87b8` and `__DOS`'s) |
| `0xfe87bc` | `gsx_mret` (`src/aes/gsxif.c`, ships `src/aes/gsxif.S`) | 1 row + 1 Line-F + 2 `.S` | 6 / 144 both answers | **1.46** both answers (T); `.S` **1.00** ×2 | ✅ verified | gl_tmp's buffer, then gl_mlen (`$c920`, staged non-zero) read after the address is stored (the address over gl_mlen); tagged; odd. ROM finding: NOTHING in the AES writes gl_mlen (GEM's gsx_malloc set it; TOS 1.02's does not), so the save buffer's length is always reported 0 |
| `0xfe8808` | `gsx_init` (`src/aes/gsxif.c`) | 1 row + 1 Line-F | 25465 / 424270 the AES's start-up | **0.95** the AES's start-up (V, `net`) | ✅ verified | the AES's start-up over the snapshot (low): gsx_wsopen, gsx_start, the AES's interrupt glue, vq_mouse into xrat/yrat; 1.06 with its thunks |
| `0xfe8828` | `gsx_graphic` (`src/aes/gsxif.c`) | 3 rows + 1 Line-F | 6 / 98 the mode held, 14584 / 175204 into alpha mode, 14460 / 174094 back into graphics | **1.24** the mode held (accepted (A)), **0.90** into alpha mode (V, `net`), **0.87** back into graphics (V, `net`) | ✅ verified | held (1 / 0 / `$ffff`); a WORD compare (`$0100` against 0 is a change); into alpha (escape 3 + gsx_resetmb), into graphics (escape 2 + the AES's glue), the sequence alpha → graphics. The mode held is ACCEPTED at 1.24 (58 → 72 own cycles): the split displacement (`lea $6486(a0)` / `cmp.w $6486(a0)`) is the C's floor, counted from the instructions (16+8+12+12+8+16); no `.S` is possible (the other arms make the escapes' Line-F call). 1.08 / 1.03 with thunks. ROM finding: its into-graphics arm is never taken by the ROM (start-up `$fead68` holds the mode, shutdown `$fead9a` goes to alpha) — staged here |
| `0xfe883e` | `gsx_setmb_aes` (gsx_graphic's tail, `src/aes/gsxif.c`) | 1 row | 286 / 4934 over the defaults | **0.81** over the defaults (V, `net`) | ✅ verified | gsx_setmb(`$fed3be` button glue, `$fed3e4` motion glue, `&drwaddr` `$947a`), entered by gsx_init's `bsr`; the two glue addresses census CODE (`addrs.AES_ROM_*_GLUE`); 0.96 with its thunks |
| `0xfe8866` | `gsx_escapes` (`src/aes/gsxif.c`) | 2 rows + 1 Line-F | 14168 / 169134 v_exit_cur, 14300 / 170422 v_enter_cur | **0.88** v_exit_cur (V, `net`), **0.88** v_enter_cur (V, `net`) | ✅ verified | escapes 2 (v_exit_cur), 3 (v_enter_cur) and 1 (vq_chcells) through contrl[5], VDI 5; its register entry `$fe886a` folded (gsx_graphic's two `bsr`s); 1.08 with its thunks |
| `0xfe8876` | `gsx_wsopen` (`src/aes/gsxif.c`) | 3 rows | 23791 / 397304 low (the snapshot's) .. 23083 / 389360 high | **1.00** low (the snapshot's) (V, `net`), **1.03** medium (V, `glue`), **1.02** high (V, `glue`) | ✅ verified | REAL opens of the physical workstation in all three ST modes (the shifter mode declared, `$8908` 2/3/4), gl_restype from the size answered; device 1 "keep the mode" ×3. 1.08 / 1.11 / 1.10 with its thunks. Its `else if` is unreachable as an `if` (a 319 × 399 answer v_opnwk never gives) |
| `0xfe88de` | `gsx_wsclose` (`src/aes/gsxif.c`) | 1 row + 1 Line-F | 4496 / 121692 the physical workstation | **0.83** the physical workstation (V, `net`) | ✅ verified | v_clswk on the physical workstation; 1.04 with its thunks |
| `0xfe88e4` | `ratinit` (`src/aes/gsxif.c`, ships `src/aes/gsxif.S`) | 1 row + 1 Line-F + 2 `.S` | 1636 / 14948 the cursor shown again | **1.47** the cursor shown again (T); `.S` **1.00** ×2 | ✅ verified | the door's depth 1 → 0, drawn; the VDI's depth 2 → 0; gl_moff := 0. ROM finding: v_show_c(0) FORCES the cursor shown (`$fcb12a` sets the depth to 1 first); v_show_c(1) counts down one (wave 1's gsx.h comment had it wrong; the constant is now GSX_SHOW_COUNTED) |
| `0xfe88f8` | `bb_set` (`src/aes/gsxif.c`) | 1 row | 10116 / 85968 a menu's corners in ptsin | **1.07** a menu's corners in ptsin (V, `glue`) | ✅ verified | the rectangle word-aligned by a LOGICAL shift (`lsr.w`: x = -8 inside one word, and a right edge past `$7fff`, one row and four, kill an arithmetic-shift mutant), gl_tmp sized, the corners (both corner arrays = ptsin; the form corners over gl_tmp's size words), vro_cpyfm S_ONLY; all five pointer arguments tagged. 1.26 with its thunks. A rectangle STRADDLING x = 0 (a `$f003`-word ROM copy) is past the oracle's cap — unpinned (`## Not reconstructed`) |
| `0xfe8966` | `bb_save` (`src/aes/gsxif.c`) | 2 rows + 1 Line-F | 10128 / 86166 the cursor hidden, 12107 / 105592 the cursor shown | **0.97** a menu's, the cursor hidden (V, `glue`), **0.96** a menu's, the cursor shown (V, `glue`) | ✅ verified | a menu (7 words, x = 21) and on words, into the snapshot's own Malloc'd buffer; a tagged rectangle; odd refused. 1.14 / 1.11 with its thunks |
| `0xfe8996` | `bb_restore` (`src/aes/gsxif.c`) | 1 row + 1 Line-F | 12148 / 106158 a menu's, the cursor shown | **0.96** a menu's, the cursor shown (V, `glue`) | ✅ verified | the sequence save → the screen scribbled → restore = the snapshot's pixels; 1.11 with its thunks |
| `0xfe89c6` | `gsx_setmb` (`src/aes/gsxif.c`) | 1 row | 280 / 4832 the AES's glue over the defaults | **0.89** the AES's glue over the defaults (V, `net`) | ✅ verified | vex_butv then vex_motv; the olds (`$c7fc`, `$c91c`) read after EACH call (two different olds staged). ROM finding: the third argument (GEM's `&drwaddr`) is never read (vex_curv's call removed); 1.06 with its thunks |
| `0xfe89f8` | `gsx_resetmb` (`src/aes/gsxif.c`) | 1 row | 277 / 4744 the defaults back | **0.88** the defaults back (V, `net`) | ✅ verified | two different olds put back; 1.07 with its thunks |
| `0xfe8a18` | `gsx_tick` (`src/aes/gsxif.c`) | 1 row + 1 Line-F | 178 / 3098 the AES's timer glue | **0.91** the AES's timer glue (V, `net`) | ✅ verified | vex_timv with the AES's timer glue (`$fed426`); the old routine laid over intout-2 / intout (each half pinned); tagged; odd refused; 1.07 with its thunks |
| `0xfe8a38` | `gsx_mfset` (`src/aes/gsxif.c`) | 2 rows + 1 Line-F | 299 / 4226 the cursor hidden, 2278 / 23908 the cursor shown | **0.92** the cursor hidden (V, `net`), **0.93** the cursor shown: hidden, set, drawn (V, `net`) | ✅ verified | 37 words copied FORWARD to where ad_intin (`$c844`) points (an overlap one word below pins the order; a form whose words are all distinct pins the 37th), vsc_form, the cursor hidden round it when shown; a tagged destination and source; odd refused. The copy is two words a pass plus the 37th (GCC emits no `dbf`): 1.10 `glue` → 0.92 `net`. 1.01 / 1.03 with its thunks |
| `0xfe8a54` | `gsx_mxmy` (`src/aes/gsxif.c`, ships `src/aes/gsxif.S`) | 1 row + 1 Line-F + 2 `.S` | 7 / 128 both answers | **1.55** both answers (T); `.S` **1.00** ×2 | ✅ verified | xrat, then yrat read after x is stored (x over yrat); tagged; odd |
| `0xfe8a6a` | `gsx_button` (`src/aes/gsxif.c`, ships `src/aes/gsxif.S`) | 1 row + 1 Line-F + 1 `.S` | 3 / 72 the left button | **1.81** the left button (T); `.S` **1.00** ×1 | ✅ verified | the buttons' word `$c90a`: 0 / 1 / 3 / `$8001` |
| `0xfe8aae` | `v_opnwk` (the AES's wrapper, `src/aes/gsxif.c`) | 1 row | 23751 / 396816 into the AES's arrays | **0.98** into the AES's arrays (V, `glue`) | ✅ verified | pb's intin/intout/ptsout(+90) pointed at the caller's arrays for the call, the handle stored BEFORE they go back (the handle over pb.intout+2); a tagged handle pointer, and tagged work_in / work_out / both (init_wk reads and answers them through the bus); 1.11 with its thunks |
| `0xfdaab0` | `gsx_start` (`src/aes/gsxif.c`) | 1 row + 1 Line-F | 1217 / 19316 the snapshot's workstation | **1.01** the snapshot's workstation (V, `glue`) | ✅ verified | the caches := -1 (incl. `$c916`, which nothing reads), the metrics, two vst_height calls (the second's four answers discarded into one stack word: host slot AES_GSX_START_DISCARD), `divs`/`muls` word semantics (ws[0] = `$9000` signed; gl_wbox's `divs` overflow pinned; a zero pixel a host "divs.w by zero" refusal), the planes loop (0/1/2/3/`$8000` colours), the five GRECTs, ad_intin; sequence wsopen(medium/high) → start. 1.11 with its thunks |
| `0xfee498` | `gsx_mfsave` (`src/aes/gsxif.c`, lbcopy's `.S` through glue) | 1 row + 1 Line-F | 260 / 2724 the snapshot's form | **1.07** the snapshot's form (T→) | ✅ verified | THE `$a000` BRIDGE (`include/aes/gsx.h` `gsx_linea_base`): the host checks vector `$28` → `$fc9f0c` and halts by name, then runs the VDI's linea_init C twin and answers A0; the target makes the real `$a000` word. The form at `*$9560` saved to `$9564`; save → restore round trip |
| `0xfee4c0` | `gsx_mfrestore` (`src/aes/gsxif.c`, lbcopy's `.S` through glue) | 1 row + 1 Line-F | 236 / 2162 a changed form | **1.07** a changed form (T→) | ✅ verified | the saved form lbcopied back to `*$9560` |
| `0xfda7f8` | `gsx_sclip` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 252 / 3696 clipping on, 198 / 3126 clipping off | **1.04** a GRECT: clipping on (V, `glue`), **0.96** no height: clipping off (V, `net`) | ✅ verified | the four clip words each read and stored in order, vs_clip on/off (h tested as moved, w read back); over the clip words and over ptsin. 1.13 / 1.06 with its thunks |
| `0xfda846` | `gsx_gclip` (`src/aes/gemgraf.c`, ships `src/aes/gemgraf.S`) | 1 row + 1 Line-F + 1 `.S` | 7 / 152 the clip out | **1.71** the clip out (T); `.S` **1.00** ×1 | ✅ verified | every store → read link chained (x over yclip, y over wclip, w over hclip) |
| `0xfda864` | `gsx_chkclip` (`src/aes/gemgraf.c`, ships `src/aes/gemgraf.S`) | 3 rows + 1 Line-F + 3 `.S` | 24 / 252 each | **1.99** inside (T), **1.99** past the clip's bottom (T), **1.99** touching its top-left (T); `.S` **1.00** ×3 | ✅ verified | sums that wrap as words (x+w, y+h, the clip's edge). ROM finding: x+w (y+h) EQUAL to the clip's x (y) still counts as touching (`blt`, not `ble`) |
| `0xfda8d2` | `gsx_cline` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 3582 / 32698 a diagonal, 7528 / 69400 the cursor hidden round it | **0.79** a diagonal (V, `net`), **0.85** the snapshot's cursor hidden round it (V, `net`) | ✅ verified | moff → v_pline(2, its own frame: host slot) → mon; PB_PTSIN back at ptsin. 0.90 / 0.97 with its thunks |
| `0xfda8e6` | `gsx_attr` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 307 / 4960 both new, 23 / 348 both cached | **0.75** text: mode and colour both new (V, `net`), **0.90** text: both cached (V, `net`) | ✅ verified | the caches `$c848` / `$971a` / `$c904`; intin[0] saved FIRST and restored after its calls; contrl's counts and handle. One address register for contrl (`near_contrl`) took the cached arm 1.21 → 0.90. 0.84 with its thunks (the cached arm makes no call) |
| `0xfda956` | `gsx_bxpts` (`src/aes/gemgraf.c`, ships `src/aes/gemgraf.S`) | 1 row + 1 `.S` | 17 / 230 a box's corners | **2.07** a box's corners (T); `.S` **1.00** ×1 | ✅ verified | the GRECT read whole first (laid above and below ptsin); no Line-F word (`bsr`-only) |
| `0xfda97c` | `gsx_box` (`src/aes/gemgraf.c`) | 1 row + 1 Line-F | 2084 / 22838 a box | **0.85** a box (V, `net`) | ✅ verified | bxpts then the polyline; 1.05 with its thunks |
| `0xfda9ce` | `gsx_blt` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 4578 / 39954 an icon's form in two colours, 7314 / 62030 the screen onto the screen | **1.01** an icon's form in two colours (V, `glue`), **0.97** the screen onto the screen (V, `glue`) | ✅ verified | vrt_cpyfm (fg ≠ -1) / vro_cpyfm; the height read once before gsx_fix(src) and reused for gsx_fix(dst); moff between the two fixes; form → form. 1.22 / 1.18 with its thunks |
| `0xfdaa48` | `bb_screen` (`src/aes/gemgraf.c`) | 1 row + 1 Line-F | 7339 / 62380 a screen rectangle | **0.98** a screen rectangle (V, `glue`) | ✅ verified | a screen-to-screen blit through gsx_blt; 1.16 with its thunks |
| `0xfdaa6a` | `gsx_trans` (`src/aes/gemgraf.c`) | 1 row + 1 Line-F | 424 / 5580 a standard form | **0.97** a standard form (V, `glue`) | ✅ verified | gsx_fix(dst) FIRST, then src, then gl_src's standard flag and planes as one long ($00010001); vrn_trnfm; widths; a tagged source / destination / both, stored as given and reached through the bus. 1.28 with its thunks |
| `0xfdac28` | `bb_fill` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 8394 / 73306 every cache new, 8713 / 77962 every cache hit | **0.87** every cache new (V, `net`), **0.93** every cache hit (V, `net`) | ✅ verified | gl_tcolor read before gsx_attr(1, mode, it); the interior/style caches compared, stored, gsx_1code(23/24). ROM finding: it passes gsx_attr the text colour's OWN cache, so only the writing mode can change there. 1.02 / 1.08 with its thunks |
| `0xfdaca4` | `gsx_tcalc` (`src/aes/gemgraf.c`, xstrpix's `.S` through glue) | 3 rows + 1 Line-F | 82 / 1070 IBM: the text fits .. 45 / 638 small: an empty string, the cell too tall | **1.05** IBM: the text fits (T→), **1.07** small: the cell too tall (T→), **1.10** small: an empty string, the cell too tall (T→) | ✅ verified | xstrpix to ad_intin, the width over intin and w/h/count chained; `divs` overflow (cell -1); a zero cell a host refusal. The empty string in the small font is AT THE BAR (1.097, `## Not reconstructed`). ROM finding: the count is xstrpix's BYTE count — a string of 256+ characters wraps (pinned with 300) |
| `0xfdad0a` | `gsx_tblt` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 2799 / 33008 the cached font, 1254 / 14298 the font changed | **0.98** the cached font (V, `net`), **1.03** the font changed (V, `glue`) | ✅ verified | the font table `$fdad74` as constants (vst_height's argument order), both directions (→ IBM, → small); the font-change arm opts out of poison (vst_height reads PTSIN before putting it back; stand-in: every stored word staged stale). ROM finding: it never sets the block's PTSIN — v_gtext reads PTSIN as the last call left it (pinned). 1.05 / 1.12 with its thunks |
| `0xfdada4` | `gsx_xbox` (`src/aes/gemgraf.c`) | 1 row + 1 Line-F | 3308 / 44112 a dotted box | **0.82** a dotted box (V, `net`) | ✅ verified | four xlines (gsx_xline inlined); 0.96 with its thunks |
| `0xfdadce` | `gsx_xcbox` (`src/aes/gemgraf.c`) | 1 row + 1 Line-F | 5651 / 78946 a box's dotted corners | **0.86** a box's dotted corners (V, `net`) | ✅ verified | ported store by store in ptsin (every `move.l (a3),-(a3)` pair); over ptsin; 0.99 with its thunks |
| `0xfdae38` | `gsx_xline` (`src/aes/gemgraf.c`) | 2 rows | 2165 / 29880 three dotted segments, 150 / 2554 one point | **0.82** three dotted segments (V, `net`), **0.90** one point: no segment (V, `net`) | ✅ verified | the dotted style's parity (x ^ y / y0 / y1); a signed direction from a negative x; the points over intin; no Line-F word (`bsr`-only). 0.95 / 1.02 with its thunks |
| `0xfda56e` | `gr_inside` (`src/aes/gemgraf.c`, ships `src/aes/gemgraf.S`) | 1 row + 1 Line-F + 1 `.S` | 9 / 140 in by 2 | **1.48** in by 2 (T); `.S` **1.00** ×1 | ✅ verified | a GRECT shrunk by a thickness (doubled: the 2t wrap) |
| `0xfda582` | `gr_rect` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 8487 / 71468 solid, 8823 / 77302 a pattern | **0.89** solid (V, `net`), **0.87** a pattern (V, `net`) | ✅ verified | interior 0 / 7 / else; vsf_color BEFORE the GRECT is read (the GRECT over intout); 1.01 / 1.00 with its thunks |
| `0xfda5c2` | `gr_just` (`src/aes/gemgraf.c`, xstrpix's `.S` through glue) | 2 rows + 1 Line-F | 117 / 1626 centred, small, 113 / 1606 right, IBM | **0.99** centred in the small font (T→), **1.00** right in the IBM font (T→) | ✅ verified | D0 = the saved D0 slot's count; the half-spare of `$7fff`, a spare of one; the corner read AFTER gsx_tcalc (a GRECT over intin) |
| `0xfda62c` | `gr_gtext` (`src/aes/gemgraf.c`) | 2 rows + 1 Line-F | 4751 / 56004 centred, small, 1870 / 20532 centred, IBM | **0.92** centred, small font (V, `net`), **0.95** centred, IBM font (V, `net`) | ✅ verified | the copy over its saved D0/D1; `tst.w; ble`; 0.96 / 1.01 with its thunks |
| `0xfda66a` | `gr_crack` (`src/aes/gemgraf.c`, ships `src/aes/gemgraf.S`) | 2 rows + 1 Line-F + 2 `.S` | 29 / 358 replace, 27 / 334 transparent | **1.44** replace (T), **1.46** transparent (T); `.S` **1.00** ×2 | ✅ verified | border, text, pattern, mode, interior in that order; all answers one word; the bit-7 test on pattern+1 |
| `0xfda6c4` | `gr_gicon` (`src/aes/gemgraf.c`) | 4 rows + 1 Line-F | 16731 / 170756 plain, a character .. 4602 / 42686 an empty label | **0.98** plain, a character (V, `net`), **0.97** selected, a character (V, `net`), **1.00** whitebak over white: no mask (V, `net`), **1.01** whitebak over white: an empty label (V, `glue`) | ✅ verified | mask, data, character, text box; the icon GRECT read AGAIN after each blit (over ptsin); the text box over ptsin; no-character intin; `$fda76e` (its blit) folded. The worst row is the empty label (1.11 with its thunks; the others 1.09 / 1.08 / 1.08). ROM finding: it pushes an extra word (2) under gr_gtext's frame — GEM's dropped `tmode`, never read |
| `0xfda7a4` | `gr_box` (`src/aes/gemgraf.c`) | 3 rows + 1 Line-F | 4258 / 46876 two lines thick .. 12131 / 126126 the cursor hidden round it | **0.71** two lines thick (V, `net`), **0.72** one line out (V, `net`), **0.76** the snapshot's cursor hidden round it (V, `net`) | ✅ verified | the zero test first (no moff/mon); gsx_box inlined. ROM finding: a NEGATIVE thickness draws -t+1 lines (`subq #1` first); -32768 (reachable through te_thickness, `$fed22a`) wraps to 32767 — unpinned (`## Not reconstructed`). 0.88 / 0.89 / 0.91 with its thunks |
| `0xfe85b0` | `gr_setup` (`src/aes/grlib.c`) | 1 row + 1 Line-F | 587 / 8984 black | **0.84** black (V, `net`) | ✅ verified | XOR mode, the colour, the solid line style, clipped to gl_rscreen (`$98a4`, the whole screen — the design note said gl_rfull). gr_watchbox (band 3) reads this routine's own `move.l #$98a4` immediate at `$fe85b2` as DATA (census CODE_BYTES; `## Not reconstructed`). 0.92 with its thunks |
| `0xfe8472` | `gr_scale` (`src/aes/grlib.c`) | 2 rows + 1 Line-F | 650 / 9940 a window's way, 619 / 9432 no distance | **0.84** a window's way (V, `net`), **0.77** no distance (V, `net`) | ✅ verified | the step count from `lsr.w` of x+y (-32768 gives 15 steps; the step's floor 1); the arguments all one word. The map had it as gr_stepcalc (swapped). 0.89 / 0.84 with its thunks |
| `0xfe82e6` | `gr_stepcalc` (`src/aes/grlib.c`) | 1 row | 696 / 10556 an icon in a window | **0.83** an icon in a window (V, `net`) | ✅ verified | the half-difference `$fe82d6` folded; overlaps cx = rect.h, cx = cy, count = cx, cx = rect.y; no Line-F word (`bsr`-only). 0.88 with its thunks |
| `0xfe83be` | `gr_xor` (`src/aes/grlib.c`) | 3 rows + 1 Line-F | 13332 / 177568 a box stepped three times .. 22720 / 316928 corners growing | **0.82** a box stepped three times (V, `net`), **0.86** corners growing (V, `net`), **0.86** corners shrinking (V, `net`) | ✅ verified | the GRECT is the caller's argument block (a host slot); count `$ffff` is unreachable (every caller hands it gr_scale's ≤ 15). 0.95 / 0.98 / 0.99 with its thunks |
| `0xfe8402` | `gr_movebox` (`src/aes/grlib.c`) | 1 row + 1 Line-F | 52641 / 729332 down and right | **0.80** down and right (V, `net`) | ✅ verified | across only, down and right; 0.93 with its thunks |
| `0xfe8340` | `gr_growbox` (`src/aes/grlib.c`) | 1 row + 1 Line-F | 129965 / 1816122 an icon to a window | **0.84** an icon to a window (V, `net`) | ✅ verified | the shared prologue `$fe831e` folded (it reads its CALLER's arguments); `from` and `to` over ptsin (+0 / +4 / +8), re-read each pass; 0.96 with its thunks |
| `0xfe837a` | `gr_shrinkbox` (`src/aes/grlib.c`) | 1 row + 1 Line-F | 129670 / 1812978 a window to an icon | **0.84** a window to an icon (V, `net`) | ✅ verified | `to` over ptsin at +0 / +4 / +8, re-read each pass (the ROM's run ends — 2,000,000-instruction budget); `to` over intout; 0.97 with its thunks |
| `0xfddec6` | `far_call` (`src/aes/obuser.c`) | 1 row | 20 / 320 a logger answering SELECTED | **0.76** a logger answering SELECTED | ✅ verified | ob_user's only call site (`$f118` at `$fe9a80`), direct and through Line-F; `staged_call.h`'s call_alcyon_pointer now ANSWERS D0 whole (on target D0 is held live across the `jsr` by an empty-asm output, so sh_find stays byte-identical — `cmp` of the .o, bench and shipped flags; its Tier 3 rows unchanged); the answer checked as 0, SELECTED and a whole longword; a top-byte code pointer jumps through 24 lines (bus_dereference is the identity on target) |
| `0xfe99a4` | `ob_format` (`src/aes/obuser.c`) | 7 rows + 1 Line-F | 104 / 1334 an empty template .. 814 / 8468 the selector's path, a full path | **0.82** the selector's path (T→), **0.81** the desk's size, right (T→), **0.80** the desk's file name (T→), **0.83** a file name, set by the desk (T→), **0.83** a size too long, right, set by the desk (T→), **0.87** the selector's path, a full path (T→), **0.66** an empty template (T→) | ✅ verified | every editable field of both resources through just_draw's own buffers (the ODD `AES_TMPLT` `$b7a7` a byte at a time); a raw text not starting '@' seeded by the ROM's own inf_sset; TE_LEFT / TE_RIGHT / TE_CNTR (merged as left), te_just compared as a WORD (`cmpi.w #1`: `$0101`, 5, -1 merge from the left); placeholder with raw left or spent; overlap cases for the '@' clear before strlen(tmplt), the forward re-read (out = tmplt+1), the NUL stored after strlen(raw) and a right merge over its own raw text; all three pointers tagged; both call words (`$f92c` ob_edit, `$f13c` just_draw). The worst row is a FULL 38-character path (every placeholder on the raw-copy arm, the dearest per byte; R2's estimate 0.88). Lengths ≥ 32768 unpinned (a word strlen; no buffer reaches it — just_draw's are 81 bytes). ROM findings: the output's end pointer is stored at -4(a6) and never read; the '@' test runs BEFORE strlen(tmplt), so a raw text that is also the template empties it |
| `0xfe9a46` | `ob_user` (`src/aes/obuser.c`) | 1 row + 1 Line-F | 152 / 2040 a USERDEF on the selector answering SELECTED | **0.79** a USERDEF on the selector answering SELECTED (T→) | ✅ verified | the PARMBLK built at -30(a6) in host slot AES_OB_USER_PARMBLK (`$7f540`, 30 bytes; `aes.RECORDS`' PARM, its fields tiled); a staged 68000 routine (`test/aes_obuser.py`, the shared USERDEF door) logs its CONTENTS whole — tree, object, prev/curr (one longword from 22(a6): pb_prevstate = curr, pb_currstate = new), rect, clip (the snapshot's and a staged one), ub_parm — and answers 0 / SELECTED / a whole long (`$87650003`); rect, userblk and ub_code tagged. The read order of ub_parm/ub_code against rc_copy/gsx_gclip is unobservable (those callees write only the frame, which differs between the shores) |
| `0xfe9a88` | `just_draw` (`src/aes/objdraw.c`) | 17 rows + 1 Line-F | 114 / 1640 a hidden object .. 61720 / 562872 an outlined dialog root | **0.77** an outlined dialog root (V, `net`), **0.80** a default exit button (V, `net`), **0.82** a BOXCHAR (V, `net`), **0.85** an FBOXTEXT path field (V, `net`), **0.84** an FBOXTEXT, right (V, `net`), **0.83** a BOXTEXT (V, `net`), **0.94** an image (V, `net`), **0.87** a string (V, `net`), **0.87** a checked menu item (V, `net`), **0.95** an icon (V, `net`), **0.86** a box outside the clip (V, `net`), **0.81** a menu's drop-down (V, `net`), **0.86** an FTEXT, seeded (V, `net`), **0.84** a USERDEF answering SELECTED (V, `net`), **0.70** a hidden object (V, `net`), **0.85** a shadowed box (V, `net`), **0.82** a crossed box (V, `net`) | ✅ verified | every type × state cell over the snapshot's own trees (walked by link: the AES's rsc, the desk's, gl_mntree, the desk's icon tree `$181d2`, the window tree); the cells no real data reaches (SHADOWED, CROSSED, FTEXT, USERDEF, an IBOX border, the small font, HIDETREE, spec -1, types outside 20..32) STAGED on real objects; tree 2's TEXT drawn as sh_draw leaves it (te_ptext = the shell's buffer via ad_pfile `$c7a2`, the whole screen's clip); the default machine's IBM font is the ROM's own gsx_tblt(IBM) write-delta (vst_height made), pinned by the menu title redrawn onto the snapshot's own pixels; a border colour ≠ the text colour, a picked BOXTEXT (as ob_change sets it), a title wider than its label, a check mark with ad_intin moved; packed-longword carries/borrows pinned (OUTLINED y<3, CROSSED h=0 at y 0 and the y+h-1 carry, ICON ib_y carry); order cases over AES_EDBLK/AES_BI/AES_IB/AES_TMPLT/intin; the 48-byte frame (one host slot in `link #-48`'s layout) staged STALE on both shores (it pinned the BUTTON's `clr.l`); nine label/font cases unpoisoned, each measured (a label reads PB_PTSIN before any call points it). 0.91–1.06 with its thunks (1.06 the icon and the image; the hidden object makes no call). ROM findings: a SHADOWED TITLE's shadow colour is an unset frame word; gl_width/8 computed and never read |
| `0xfea028` | `ob_draw` (`src/aes/obdraw.c`, `src/aes/obdraw.S`) | 9 rows + 1 Line-F | 28137 / 361544 the alert, unbuilt .. 187669 / 1875778 the menu bar | **0.84** the menu bar (V, `net`), **0.82** a desk dialog (V, `net`), **0.82** a desk dialog redrawn (V, `net`), **0.89** the desk's icons (V, `net`), **0.80** the window tree (V, `net`), **0.80** the alert, unbuilt (V, `net`), **0.82** the selector's scroll bar (V, `net`), **0.75** the selector's root alone (V, `net`), **0.82** the selector cut by a window's corner (V, `net`) | ✅ verified | every snapshot tree drawn whole from its root at depth 8 (a first draw unpoisoned where a label reads PTSIN first — measured per tree, 16/16; every tree redrawn POISONED from the state the ROM's own first draw leaves); the desktop band as sh_draw draws it (te_ptext the shell's buffer, the whole screen's clip; root depth 1 and the TEXT alone), and under the desktop's clip its TEXT cut whole; subtrees from the parent's offset (sibling, next = parent, three deep, nine children); depth 0..3; clips cutting / missing (set by the ROM's own gsx_sclip); a USERDEF in a drawn tree; the root's ob_next unread; the position words staged STALE (pins the root's `clr.l`); Line-F `$f200`, the shown cursor, BUS_TAG. Target hands everyobj `obdraw.S`'s ALCYON ENTRY (glue, counted as T→G), RED-proved (the ROM's just_draw on target: 248,590 cycles in the AES spans, refused). 0.88–1.01 with glue (1.01 the desk's icons). The selector's whole draw (256,140 insns) is over the bench's 200,000-instruction cap: priced in a scratch run at 0.83 (0.94 with glue) |
| `0xfea38e` | `ob_change` (`src/aes/obdraw.c`) | 8 rows + 1 Line-F | 110 / 1558 the state unchanged .. 19629 / 195318 an icon picked | **0.66** a button pressed (V, `net`), **0.56** a title dropped (V, `net`), **0.83** an icon picked (V, `net`), **0.67** a menu item unchecked (V, `net`), **0.77** a button disabled (V, `net`), **0.70** the state unchanged (V, `net`), **0.73** no redraw (V, `net`), **0.54** a USERDEF answering SELECTED (V, `net`) | ✅ verified | XOR in place (border -3 → 0, 1, 2; a dropped title under the whole screen's clip); an icon / any other change redrawn whole (the state stored before the draw); a state changed only in its HIGH byte (word compare); SELECTED+DISABLED only XORed; the USERDEF answer unread (0 and SELECTED identical); unchanged / spec -1 / redraw 0 return early; redraw `$0100` (`tst.w`); the inset corner's packed carry (y -2, border 2); the 20-byte frame (host slot, `link #-20`'s layout) staged STALE; Line-F `$f214` and `$f098` (gr_watchbox), the shown cursor, BUS_TAG. 0.57–0.91 with its thunks. ROM findings: only SELECTED is inverted (another bit's mark waits for a redraw); an ICON is always redrawn whole; the inset is one `add.l` (y in [-th,-1] carries into x); the early returns skip moff/mon |
| `0xfe8508` | `gr_stilldn` (`src/aes/grwait.c`, ships as C: it makes a Line-F call) | 7 rows + 1 Line-F | 827 / 12470 the button down, outside, waiting to leave .. 833 / 12576 the button up, waiting to enter | **1.04** every row (EV, `net`) | ✅ verified | THE EVENT DOOR's first user: ev_multi's every REACHABLE outcome over gr_stilldn's events, each over a machine the ROM's own scheduler produced — the rise (the button up: waiting to leave, waiting to enter where the rise wins over the rectangle, outside waiting to enter) and the rectangle's event (the button down: inside waiting to enter, outside waiting to leave, an empty rectangle at the mouse waiting to leave, a rectangle at negative words waiting to enter); the waits nothing satisfies are REFUSED by the door ("would block", in a child process), not rows; the frame each door call hands (the MOBLK dereferenced, mouse2/timer/message) compared with the ROM's own call's; direct and through Line-F `$f0b0`. Own 354 cycles against the ROM's 340, one door window per row, equal on both sides; whole run 1.00. The target pushes the already-zero A1 for the constant-zero arguments (1.09 → 1.04). Mutation (strict, no `-x`): 14 — 14 killed |
| `0xfe84ba` | `gr_watchbox` (`src/aes/grwait.c`) | 4 rows + 1 Line-F | 1502 / 21798 OK, drawn normal while inside .. 10873 / 133980 the arrow, crossed while inside | **0.63** OK, selected while inside (V+EV, `net`), **0.63** Cancel (V+EV, `net`), **0.74** the arrow, crossed while inside (V+EV, `net`), **0.62** OK, drawn normal while inside (V+EV, `net`) | ✅ verified | the first pass ending on the button's rise over OK, Cancel and the TOUCHEXIT arrow, in/out states SELECTED / NORMAL / CROSSED and NORMAL-in, over PD0 running (scheduler-derived); the rectangle ob_actxywh answers, its x/y order and the leave flag handed to gr_stilldn pinned by the door's frame compare (R1's three holes); the tree through the 24-bit bus; the clip gl_rscreen BY VALUE (not the ROM's `*$fe85b2` read of gr_setup's immediate); through Line-F. 0.66 / 0.66 / 0.82 / 0.63 with thunks, whole run 0.88–0.95. The SECOND pass pinned up to its wait: over the button down with OK, Cancel or the arrow outside the mouse, pass 1 answered, the `out` state drawn, pass 2's wait refused by the door (child) — the object's state and both handed frames held to the ROM's run stopped where it blocks; its 0 answer unpinned (`## Not reconstructed`). Mutation (strict, no `-x`): 11 — 11 killed (the `in` state drawn every pass caught by the second pass's pin alone) |
| `0xfebdbe` | `ap_sendmsg` (`src/aes/apmsg.c`) | 3 rows + 1 Line-F | 754 / 9576 to PD0 running: into its pipe .. 981 / 12486 from the screen manager to PD0 parked | **0.57** from the screen manager to PD0 parked: handed to its wait (EV, `net`), **0.57** to PD0 running: into its pipe (EV, `net`), **0.57** a second behind the first (EV, `net`) | ✅ verified | sent BY PD1 running (the screen manager, woken by the mouse on the menu bar) to PD0 parked: handed to PD0's message EVB, PD0 onto drl, sender word 1; to PD0 running (into its pipe); a second message behind the first (appended); a redraw for the same window (MERGED by ap_rdwr); to PD1 (its pipe); the sender read after the type's store (the buffer over PD0's pid); rlr and the buffer through the 24-bit bus; an odd buffer refused (child); through Line-F. Whole run 0.97–0.98. Mutation: 11 — 9 killed, 2 equivalent (the answer dropped: ap_rdwr answers 0 in every reachable machine; rlr masked to 16 bits: every PD lives below `$10000`) |
| `0xfe4a98` | `ct_mouse` (`src/aes/ctrl.c`) | 4 rows + 2 Line-F | 608 / 7058 a release after a hidden grab .. 2582 / 26952 a grab, the cursor shown | **0.94** a grab, the cursor shown (V, `net`), **0.94** a grab, the cursor hidden: shown (V, `net`), **0.94** a release after a hidden grab (V, `net`), **0.93** a release after a shown grab: re-shown (V, `net`) | ✅ verified | no door (a band-4 leaf ported in band 3), runs POISONED: the grab with the cursor shown / hidden (v_show_c(0)), the arrow set; the release after a hidden grab, and after a shown grab (the re-show) with the stack's word ≠ the C's (contrl[3] dropped by name — the ROM hands gsx_ncode two words where it takes three) and = the C's (compared whole); the release machines derived from the ROM's own grab run; through Line-F (grab, release). 1.00–1.02 with thunks. Mutation: 16 — 16 killed |
| `0xfe9260` | `ob_getsp` (`src/aes/obedit.c`) | 3 rows + 1 Line-F | 143 / 1566 the path .. 145 / 1580 an INDIRECT selection | **0.77** the path (T→), **0.77** the desk's size (T→), **0.77** an INDIRECT selection (T→) | ✅ verified | INDIRECT is OB_FLAGS' HIGH byte bit 0 (a `btst` of the word in the frame; `$0001`/`$0200` are not); lbcopy of 28; bus tags; through Line-F |
| `0xfe9352` | `scan_to_end` (`src/aes/obedit.c`) | 2 rows + 1 Line-F | 102 / 990 the dot, from the head .. 368 / 3180 absent: the whole path's template | **0.57** the dot, from the head, **0.67** absent: the whole path's template | ✅ verified | a byte compare of the character's LOW byte (its high byte ignored); the character stop, the NUL stop, '_' counted after the post-increment, empty; the template tagged |
| `0xfe937e` | `ins_char` (`src/aes/obedit.c`) | 2 rows + 1 Line-F | 66 / 780 at its end .. 576 / 4560 at a long text's head | **0.64** at a long text's head (T→), **0.65** at its end (T→) | ✅ verified | mid / end / start / empty; room > n+1, = n+1, < n+1, 0, -1 — compared SIGNED (room ≤ 0 stores below the string); a negative `at`; the string tagged; also fs_back's |
| `0xfe93da` | `find_pos` (`src/aes/obedit.c`) | 3 rows + 1 Line-F | 35 / 448 the selection's first .. 750 / 4896 an 80-place template's last place | **1.06** an 80-place template's last place, **1.01** the path's last place, **0.46** the selection's first | ✅ verified | every real template × 4 indices; the walk reading on past the NUL for an index beyond the placeholders; a negative index; no placeholders; the template tagged at index 2 (both walks read through the tag); 80 placeholders (the longest field the 81-byte buffers hold) is the worst row |
| `0xfe941c` | `pxl_rect` (`src/aes/obedit.c`) | 3 rows + 1 Line-F | 501 / 6552 the selector's centred title .. 657 / 7912 the path's first cell | **0.66** the path's first cell (T→), **0.63** a size, right-justified (T→), **0.62** the selector's centred title (T→) | ✅ verified | left / right / centred, the small font (te_font 5 staged), negative and word-wrapping positions, gl_wchar re-read; host slot AES_PXL_RECT_FIELD; gr_just's count stored at -10(a6), never read |
| `0xfe948a` | `curfld` (`src/aes/obedit.c`) | 5 rows | 1930 / 26966 the cursor at the selector's centred title .. 42030 / 474158 the whole path redrawn | **0.71** the cursor at the path's first cell (V, `net`), **0.70** the cursor at a size, right-justified (V, `net`), **0.70** the cursor at the selector's centred title (V, `net`), **0.78** the whole path redrawn (V, `net`), **0.78** one cell redrawn (V, `net`) | ✅ verified | the cursor (an XOR line, y-3..h+6) on 4 fields; redraw n = 1, 8, 38, past the end, -2, `$0100` (`tst.w`); an object with children (depth 0); host slot AES_CURFLD_RECTS; the stretch redraws unpoisoned (PTSIN read first, measured), the object-alone redraw POISONED (a G_BOX), the arm poisoned inside every redrawing EDCHAR. 0.74–0.84 with thunks, whole run 0.88–0.99 |
| `0xfe9516` | `instr` (`src/aes/obedit.c`) | 4 rows + 1 Line-F | 42 / 522 a bar through set 4 .. 242 / 1974 a bar through set 6 | **0.59** a bar through set 4, **0.98** a bar through set 6 (STANUM), **0.96** a bar through set 7, **0.89** a bar through set 12 | ✅ verified | singles, "a..z" ranges, the real sets 4..12, SIGNED byte compares (staged " ..\xff" empty, "\x80.. "), a range ending at the NUL walking on past it |
| `0xfe9556` | `check` (`src/aes/obedit.c`) | 6 rows + 1 Line-F | 45 / 578 'X' .. 588 / 6114 'N' refusing a bar | **0.52** 'P' refusing a bar (T→), **0.59** 'N' refusing a bar (T→), **0.37** 'n' taking 'z' (T→), **0.43** 'x' upcasing (T→), **0.23** 'X' (T→), **0.34** an unknown one (T→) | ✅ verified | all 11 validation characters (table `$fefb10`) × 9 characters, NUL / '#' / `$b9`, the low-byte rule (`$4139`/`$4158`/`$4178`); rs_str called BEFORE the character is read (the character on AES_RS_STRING); 'f' and 'p' upcase too. Mutation: 3 equivalent survivors (`## Not reconstructed`) |
| `0xfe95f2` | `ob_stfn` (`src/aes/obedit.c`) | 3 rows + 1 Line-F | 135 / 1688 an empty selection .. 1873 / 13222 an 80-place field, full | **1.04** an 80-place field, full (T→), **0.95** a full path (T→), **0.32** an empty selection (T→) | ✅ verified | 4 real fields; start over AES_RAWSTR (stored before strlen(raw)); one pointer for both; find_pos's `CURSOR_BARRIER` holds the inlined template in a register (1.17 → 0.95, measured) |
| `0xfe962a` | `ob_delit` (`src/aes/obedit.c`) | 2 rows + 1 Line-F | 19 / 252 at the end .. 123 / 1440 a long text's head | **0.81** a long text's head (T→), **0.42** at the end (T→) | ✅ verified | mid / last / end / empty / first; a negative index (the byte below the buffer) |
| `0xfe9678` | `ob_edit` (`src/aes/obedit.c`) | 15 rows + 1 Line-F | 28 / 480 EDSTART .. 56584 / 622606 a character at an 80-place field's head | **0.80** EDINIT, an application's 80-place field (V, `net`), **0.80** a character at an 80-place field's head (V, `net`), **0.76** EDINIT, a full path (V, `net`), **0.75** a character at a full path's head (V, `net`), **0.76** BS at a full path's head (V, `net`), **0.76** DEL at a full path's head (V, `net`), **0.75** ESC over a full path (V, `net`), **0.66** a refused character past the last place (V, `net`), **0.32** EDSTART (V, `net`) | ✅ verified | every EDITABLE of both resources (10 fields) and non-editable real TEDINFOs; EDSTART, the root, -1, -32768 store nothing; EDINIT on empty and inf_sset-seeded texts; EDEND, 4, `$7fff`, -1, `$0101` (word compare); every EDCHAR case from the ROM's own EDINIT (+ keys) but the two that are an application's objc_edit(EDCHAR) without one; typed P/F/X/x/a, refusals, `$e9`, mid-text, past the last place, the literal fills, a NUL key; ESC/BS/DEL/LEFT/RIGHT at every position; validation strings of 255 / 256 characters (lstcpy's byte count); the refused key's un-stepped start (D3) pinned at index `$7fff` (the save-under buffer staged as placeholders, 1.1 s); an INDIRECT spec; the order and overlap cases; bus tags on the tree, the index and a TEDINFO's three pointers; host slot AES_OB_EDIT_FRAME; Line-F `$f210`. Whole run 0.80–0.96 (0.32 EDSTART), 0.70–0.83 with thunks |
| `0xfeb3c0` | `w_nilit` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 186 / 2478 the window tree .. 406 / 5426 W_ACTIVE | **0.39** W_ACTIVE, **0.39** the window tree | ✅ verified | counts 19 / 8 / 0; a tagged array; the negative count (round the word) unpinned — every caller passes a constant |
| `0xfeb408` | `w_obadd` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 48 / 718 after a last child .. 49 / 730 a first child | **0.59** a first child, **0.63** after a last child | ✅ verified | ob_add's body byte for byte (the C calls aes_ob_add); both -1 arms |
| `0xfeb47a` | `w_setup` (`src/aes/wmlib.c`) | 1 row + 1 Line-F | 34 / 504 a closed window | **0.60** a closed window | ✅ verified | flags OR-ed (BROKEN kept); the owner stored whole (tagged) |
| `0xfeb57c` | `w_setsize` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 80 / 1102 | **0.51** the full rectangle (T→), **0.52** the current rectangle (T→) | ✅ verified | the four WS_*; a tagged rectangle |
| `0xfeb594` | `w_adjust` (`src/aes/wmlib.c`) | 1 row + 1 Line-F | 119 / 1738 the title bar | **0.37** the title bar | ✅ verified | the first child; over a built tree (old children dropped); the ROM's rc_copy of its own argument words spelt as four stores |
| `0xfeb5f8` | `w_hvassign` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 160 / 2294 .. 161 / 2302 | **0.44** a vertical arrow, **0.44** a horizontal arrow | ✅ verified | both frame layouts |
| `0xfeb646` | `w_clipdraw` (`src/aes/wmlib.c`) | 3 rows + 1 Line-F | 26 / 392 drawing held .. 108019 / 1054830 the desktop in four pieces | **0.83** the top window's gadgets (V, `net`), **0.85** the desktop in four pieces (V, `net`), **0.62** drawing held (V, `net`) | ✅ verified | gl_wfrozen / -1 → 1; clip 0 = gl_rfull (the menu bar spared, pinned on a cleared screen); the clip cut in place; pieces the clip misses; the 4-piece loop (D0 0 from `move.l a4,d0`); the tree tagged; host slot -8(a6), `_Static_assert`ed. Whole run 0.99, 0.95–0.96 with thunks |
| `0xfeb6c8` | `w_drawdesk` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 15355 / 144814 the window tree's root .. 17369 / 169514 the desk's icons | **0.76** the desk's icons (V, `net`), **0.78** the window tree's root (V, `net`) | ✅ verified | gl_newdesk / gl_newroot (the snapshot's, none via the ROM's wind_set NEWDESK 0, an application's nested tree from root 1 six AND four levels deep: depths up to 5 and a wrong root each fail); the rectangle grown in place; depth 6 / 7 = 8 on every tree that returns. Whole run 0.96–0.98, 0.87–0.89 with thunks |
| `0xfeb712` | `w_cpwalk` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 2306 / 31484 a lower window under the clip .. 107843 / 1187078 the top window | **0.76** the top window (V, `net`), **0.40** a lower window under the clip (V, `net`) | ✅ verified | top / use_true / gclip + border (the clip set by the ROM's gsx_sclip); the rebuild pinned unpoisoned (measured); gl_awind read after w_bldactive; host slot `_Static_assert`ed. 0.86 / 0.41 with thunks |
| `0xfeb768` | `w_strchg` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 19793 / 234872 an information line .. 20438 / 239234 a title | **0.51** a title (V, `net`), **0.51** an information line (V, `net`) | ✅ verified | NAME / INFO, a lower window (use_true), window -1 (the only case whose gl_aname / gl_ainfo store survives: w_bldactive rebuilds it otherwise). Whole run 0.85, 0.55 with thunks |
| `0xfeb7ca` | `w_barcalc` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 79 / 1248 the default size .. 121 / 1926 a size per mille | **0.93** the default size (T→), **0.99** a size per mille (T→) | ✅ verified | size -1, max → min, max → computed, both bars, mul_div's rounding, a negative remaining track; size > track |
| `0xfeb84e` | `w_bldbar` (`src/aes/wmlib.c`) | 3 rows + 1 Line-F | 224 / 3134 a window below .. 981 / 13786 every vertical gadget | **0.48** every vertical gadget (T→), **0.48** every horizontal gadget (T→), **0.40** a window below (T→) | ✅ verified | 7 gadget subsets × both bars × top / below |
| `0xfeba9c` | `w_bldactive` (`src/aes/wmlib.c`) | 4 rows + 1 Line-F | 26 / 422 window -1 .. 3693 / 51454 the top window, every gadget | **0.40** the top window, every gadget (T→), **0.36** a lower window, every gadget (T→), **0.30** a window of no gadgets (T→), **0.12** window -1 (T→) | ✅ verified | 9 kinds, each a ROM wm_create + wm_open; sliders / sizes from the ROM's wm_set; the sizer spec both ways; the -1 test kept apart from the body (a noinline static `build_active`; 1.15 by the body's saves before) |
| `0xfebece` | `w_mvfix` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 75 / 942 on the screen .. 79 / 984 one pixel off the left edge | **0.66** one pixel off the left edge, **0.64** on the screen | ✅ verified | x -1 / 0 / -2; x read before the cut (overlap) |
| `0xfebf00` | `w_move` (`src/aes/wmlib.c`) | 4 rows + 1 Line-F | 24 / 410 drawing held, moved .. 83674 / 693866 the strip at the left edge | **0.66** a window moved (V, `net`), **0.47** off the right edge (V, `net`), **0.53** the strip at the left edge (V, `net`), **0.50** drawing held, moved (V, `net`) | ✅ verified | every move arm from the ROM's wm_set moves (blit; union off right / bottom; away from each edge; touching the edge `>`; the strip from -1; to -1; both fixed), the stop and rectangle pointers tagged; the stop word read back after rc_copy; the HELD arm stores nothing and leaves the CALLER's D0 (pinned; the C answers 0, not compared at Tier 1 nor Tier 3 — unreachable from draw_change `$fec172`); host slot `_Static_assert`ed. Whole run 0.53–1.00 |
| `0xfec39a` | `w_owns` (`src/aes/wmlib.c`) | 3 rows + 1 Line-F | 28 / 390 an empty list .. 344 / 4254 past every piece | **0.81** the first piece (T→), **0.75** past every piece (T→), **1.09** an empty list (T→) | ✅ verified | WIN_RNEXT; the link re-read after the copy (an unpoisoned overlap, measured); the empty list is the floor and realistic (wind_get FIRST of a window with no list) |
| `0xfec3ea` | `w_union` (`src/aes/wmlib.c`) | 3 rows + 1 Line-F | 26 / 366 no list .. 191 / 2216 four pieces | **0.92** four pieces (T→), **0.73** one piece (T→), **0.52** no list (T→) | ✅ verified | 4 pieces, one, none |
| `0xfec424` | `wm_start` (`src/aes/wmlib.c`) | 1 row + 1 Line-F | 4221 / 54598 over the snapshot | **0.45** over the snapshot (T→) | ✅ verified | the ROM tables `$fefc3c` / `$fefc62` / `$fefcae` spelt as C data (no ROM address in them); over a machine with a window open |
| `0xfec602` | `wm_create` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 103 / 1334 every window in use .. 375 / 5004 the first free window | **0.39** the first free window (T→), **0.46** every window in use (T→) | ✅ verified | the first free, all 8 in use (-1; the ROM reads window 8's flag byte `$c66f`), a freed middle one |
| `0xfec706` | `wm_delete` (`src/aes/wmlib.c`) | 1 row + 1 Line-F | 18 / 292 a window | **0.53** a window | ✅ verified | windows 1, 7, -1; D0.w = THEGLO + 56*w (the desk's binding stores it) |
| `0xfec722` | `wm_get` (`src/aes/wmlib.c`) | 7 rows + 1 Line-F | 31 / 462 past the last field .. 277 / 3592 WF_FIRSTXYWH | **0.49** WF_WORKXYWH (T→), **0.81** WF_HSLIDE (T→), **0.53** WF_TOP (T→), **0.58** WF_FIRSTXYWH (T→), **0.65** WF_SCREEN (T→), **0.47** WF_RESVD (T→), **0.51** past the last field (T→) | ✅ verified | every field 4..17 incl. 13 / 14 (no arm), 3 / 18 / -1; the FIRST → NEXT walk (NEXT unpoisoned: it reads the cursor it writes); WF_TOP none → 0; every arm's D0.w modelled (rect arms the xptr's low word, word arms (field-4)*4, TOP the top, list arms w_owns', past the table field-4); `out` tagged on every arm and through the walk; host slot `_Static_assert`ed |
| `0xfeca4a` | `wm_find` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 336 / 4374 a window's .. 368 / 4828 of nothing | **0.63** of nothing (T→), **0.65** a window's (T→) | ✅ verified | a window, the desktop, off the screen, (y,x)-asymmetric |
| `0xfecaac` | `wm_calc` (`src/aes/wmlib.c`) | 2 rows + 1 Line-F | 56 / 666 no gadget's work area .. 80 / 800 every gadget's border | **0.73** every gadget's border, **0.74** no gadget's work area | ✅ verified | 6 kinds × WC_BORDER / WORK; the store order (h last, y after x); word wrap; D0.w = the height stored |
| `0xfe5008` | `set_ctrl` (`src/aes/wmupdate.c`) | 1 row + 1 Line-F | 32 / 486 a rectangle | **0.65** a rectangle (`through`) | ✅ verified | rc_copy into the control manager's rectangle ctrl `$9b3e`; the pointer tagged; through Line-F |
| `0xfe501c` | `get_ctrl` (`src/aes/wmupdate.c`) | 1 row + 1 Line-F | 32 / 486 the control rectangle | **0.65** the control rectangle (`through`) | ✅ verified | rc_copy out of ctrl, the destination overlapping it; tagged; through Line-F |
| `0xfe5030` | `get_mown` (`src/aes/wmupdate.c`) | 1 row + 1 Line-F | 17 / 284 both owners | **0.62** both owners | ✅ verified | both owners, gl_mowner `$9afa` stored before gl_kowner `$9ad8` (the two pointers overlapping: the mouse's store first); through Line-F |
| `0xfe718e` | `fm_own` (`src/aes/wmupdate.c`) | 4 rows + 1 Line-F | 99 / 1294 taken again .. 363 / 5062 taken | **0.38** taken (EV, `net`), **0.38** taken again (EV, `net`), **0.34** given back (EV, `net`), **0.38** taken by the screen manager (EV, `net`) | ✅ verified | over tak_flag (rebound in band 4 wave 0) and the door's ct_chgown / unsync: taken, taken again (counted at `$9450`), given back (the KEYBOARD's saved owner restored first, then the menu, then the release), taken by the screen manager (PD1 running, scheduler-derived); D0 on every arm; an unbalanced give-back; BLOCKED after an unbalanced END_UPDATE (a ROM finding: tak_flag, then ev_block) — refused in a child, the whole image and every frame held to the ROM's run stopped where it blocks; through Line-F. 0.41 with thunks, whole run 0.38–0.81 |
| `0xfeba54` | `w_setactive` (`src/aes/wmupdate.c`) | 2 rows + 1 Line-F | 322 / 4452 no window: the desktop's .. 323 / 4472 the top window's | **0.37** the top window's (EV, `net`), **0.35** no window: the desktop's (EV, `net`) | ✅ verified | the top window's owner and work area, and the desktop's (gl_wtop -1 → window 0), handed to the door's ct_chgown (its frame compared); gl_wtop read twice, the signed `muls`; through Line-F. 0.39–0.41 with thunks, whole run 0.73 |
| `0xfebe2a` | `w_redraw` (`src/aes/wmupdate.c`) | 3 rows + 1 Line-F | 201 / 2600 outside the work area .. 1166 / 14748 a redraw posted | **0.55** a redraw posted (EV, `net`), **0.46** outside the work area (V, `net`), **0.54** a covered part (V, `net`) | ✅ verified | the work-area cut only gates; the visible list's bounding box replaces it; ap_sendmsg(gl_rmsg `$9adc`, WM_REDRAW) to the owner through the door's ap_rdwr; outside the work area and a covered part post nothing; gl_rmsg over the rectangle (overlap); through Line-F. 0.53–0.61 with thunks, whole run 0.53–0.86 |
| `0xfec026` | `w_update` (`src/aes/wmupdate.c`) | 4 rows + 1 Line-F | 25 / 438 drawing held .. 171103 / 1879418 two windows | **0.75** two windows (V+EV, `net`), **0.75** one window (V+EV, `net`), **0.76** no window (V, `net`), **0.20** drawing held (V, `net`) | ✅ verified | top to bottom by the prev-sibling walk: no window, one, two; drawing held (gl_wfrozen: nothing drawn); `moved` re-read each pass, the rfull cut in place; drawing cases guarded in a child first; through Line-F. 0.79–0.86 with thunks, whole run 0.20–0.96 |
| `0xfec0ca` | `draw_change` (`src/aes/wmupdate.c`) | 9 rows + 1 Line-F | 2454 / 31942 drawing held .. 180617 / 1957212 moved and resized away | **0.78** moved, the same size: blitted (V+EV, `net`), **0.77** moved and resized away (V+EV, `net`), **0.73** moved over where it was: the old inside the new (V+EV, `net`), **0.74** shrunk in place (V+EV, `net`), **0.55** unchanged on top (EV, `net`), **0.74** a lower window moved, the same size (a title bar) (V+EV, `net`), **0.74** a lower window moved, resized (a title bar) (V+EV, `net`), **0.71** a window brought to the top (a title bar) (V+EV, `net`), **0.54** drawing held (EV, `net`) | ✅ verified | everyobj over newrect handed BY VALUE — on target `src/aes/wmupdate.S`'s ALCYON ENTRIES for newrect AND mkrect (target-only glue), so no ROM AES code runs in our build (R3's blobs with the entries bypassed: every draw row REFUSED by the bench, 19,060 cycles in the AES's own spans); moved (blitted; x-only, y-only; off an edge, not blitted), moved and resized, shrunk, the old inside the new, unchanged on top, drawing held, topped (WF_TOP whole vs covered, gl_wasclr stale / whole); the OVERLAPPING-WINDOW arms priced over TITLE-BAR windows (a lower window moved, the same size and resized; a window brought to the top — with every gadget they pass the bench's 200,000-instruction cap and stay Tier 1); a far move to a zero-height and a zero-width rectangle (R1's survivor 96, a false equivalent: rc_union writes into `old`); the tail's copy of the new top's rectangle over the CALLER's; drawing cases guarded in a child first; through Line-F. 0.60–0.87 with thunks, whole run 0.63–0.99 |
| `0xfec676` | `wm_opcl` (`src/aes/wmupdate.c`) | 1 row | 112786 / 1252194 a created window added | **0.73** a created window added (V+EV, `net`) | ✅ verified | the rectangle copied before the lock; w_obadd(`$9734`, 0, w) / ob_delete(gl_wtree); w_setsize(WS_PREV) read through the CALLER's pointer AFTER draw_change (pinned by an overlap over WIN_PREV); reached by `bsr` only. 0.83 with thunks, whole run 0.95 |
| `0xfec6da` | `wm_open` (`src/aes/wmupdate.c`) | 1 row + 1 Line-F | 112814 / 1252560 a created window | **0.73** a created window (V+EV, `net`) | ✅ verified | wm_opcl(w, rect, 1) over a window the ROM's wm_create made; through Line-F. 0.83 with thunks, whole run 0.95 |
| `0xfec6f0` | `wm_close` (`src/aes/wmupdate.c`) | 2 rows + 1 Line-F | 68278 / 682502 the top window .. 191998 / 2059582 the lower window | **0.78** the top window (V+EV, `net`), **0.76** the lower window (V+EV, `net`) | ✅ verified | wm_opcl(w, &gl_rzero, 0): the top window and the lower one; through Line-F. 0.86 with thunks, whole run 0.97–0.98 |
| `0xfec83a` | `wm_set` (`src/aes/wmupdate.c`) | 10 rows + 1 Line-F | 197 / 2594 a field with no arm .. 181233 / 1978702 moved | **0.70** top: a covered window (a title bar) (V+EV, `net`), **0.75** drawing released over an area (V+EV, `net`), **0.76** moved (V+EV, `net`), **0.53** a slider of the top window (V+EV, `net`), **0.39** a slider of a lower window (EV, `net`), **0.50** a title (V+EV, `net`), **0.28** drawing held (EV, `net`), **0.28** a new desk (EV, `net`), **0.27** a field with no arm (EV, `net`), **0.73** top: a whole window (V+EV, `net`) | ✅ verified | table `$fefd16`, every field: 2 NAME, 3 INFO, 5 CURRXYWH (moved), the four sliders of the top window and of a lower one (the clamp's store, re-read, store — the read-back's words over gl_wtop), 10 TOP of a whole window and of a COVERED one (a title bar), 13 drawing held and RELEASED over an area (w_drawdesk + w_update), 14 NEWDESK, and 4 / 6 / 7 / 11 / 12 with no arm; the slider arms' dead loads; D0 under a held lock not compared (`## Not reconstructed`); through Line-F. 0.44–0.86 with thunks, whole run 0.38–0.97 |
| `0xfeca68` | `wm_update` (`src/aes/wmupdate.c`) | 6 rows + 1 Line-F | 62 / 828 one level of the lock released .. 399 / 5506 3: the screen taken | **0.48** the lock taken (EV, `net`), **0.48** the lock taken again (EV, `net`), **0.36** the lock released (EV, `net`), **0.36** one level of the lock released (EV, `net`), **0.36** 3: the screen taken (EV, `net`), **0.33** 2: the screen given back (EV, `net`) | ✅ verified | over tak_flag (REBOUND in band 4 wave 0: its C twin on both builds, an arrival with no window), the door's unsync and fm_own: the lock taken, taken again, released, one level released (unsync leaves the CALLER's D0: not compared), 3 the screen taken, 2 given back; the SIGNED `cmp.w #2; bge`; BLOCKED after an unbalanced END_UPDATE (tak_flag, then ev_block) and the HAND-OVER to a waiter REFUSED AS A YIELD (`aes_event.parked`: PD0 holds the lock and parks, PD1's BEG_UPDATE queues on it, Return wakes PD0) — each held to the ROM's run on the whole image at the refusing entry; through Line-F. 0.39 with thunks, whole run 0.48–0.76 |
| `0xfe8576` | `gr_wait` (`src/aes/grdrag.c`; gr_draw `$fe8532` and gr_xdraw `$fe8564` folded: bsr-only) | 4 rows + 1 Line-F | 6386 / 90900 the button down, the pixel away from the mouse: it left .. 12206 / 171216 the button up, two boxes | **0.82** the button up, one box: it rose (V+EV, `net`), **0.82** the button up, two boxes (V+EV, `net`), **0.82** the button down, the pixel away from the mouse: it left (V+EV, `net`), **0.82** the button down, two boxes, the pixel away (V+EV, `net`) | ✅ verified | one box and two (the twin unless poff EQUALS gl_rzero), the button risen / left; the wait at the mouse REFUSED (would block) and pinned to the ROM's block on the whole image; through interrupts at the door: released (0) and moved (1) while it waits; gl_rzero BY VALUE for `$fe8586`; through Line-F. 0.94–0.95 with thunks, whole run 0.99 |
| `0xfe86dc` | `gr_clamp` (`src/aes/grdrag.c`; its fragment `$fe86c2` folded) | 2 rows + 1 Line-F | 47 / 592 the mouse inside: its distance + 1 .. 49 / 596 left of and above it: the minimums | **0.99** the mouse inside: its distance + 1 (`through`), **1.01** left of and above it: the minimums (`through`) | ✅ verified | inside (the distance + 1), left of and above (the minimums: the longest path), negative, a word wrap; the mouse at local +0 / +2, the signed `bge`, the width first; through gsx_mxmy's glue; through Line-F |
| `0xfe85de` | `gr_rubwind` (`src/aes/grdrag.c`) | 2 rows (1 INTERRUPTED) + 1 Line-F | 14762 / 200318 a window's outline twin, 30322 / 406096 a window's outline stretched | **0.80** a window's outline twin (V+EV, `net`), **0.80** a window's outline stretched (V+EV, `net`; interrupted) | ✅ verified | a window's outline twin (the control manager's sizing, Line-F `$f790`, a real offset); through interrupts its outline stretched (priced) and its busy loop at the minimum ended by the release. 0.92 with thunks, whole run 0.99 |
| `0xfe85c6` | `gr_rubbox` (`src/aes/grdrag.c`) | 3 rows + 1 Line-F | 7103 / 102008 held at the minimum .. 8079 / 111594 stretched to the mouse | **0.79** stretched to the mouse (V+EV, `net`), **0.79** held at the minimum (V+EV, `net`), **0.79** the mouse left of the box (V+EV, `net`) | ✅ verified | stretched, held at the minimum, the mouse left of the box; the button-down wait pinned to the block; through interrupts stretched and its busy loop ended by the release; over the cursor shown and hidden; through Line-F. 0.89 with thunks, whole run 0.98 |
| `0xfe8640` | `gr_dragbox` (`src/aes/grdrag.c`) | 5 rows (1 INTERRUPTED) + 1 Line-F | 7309 / 104178 outside the bound: pulled in .. 22054 / 284590 moved, the cursor shown | **0.77** the mouse inside: it stays (V+EV, `net`), **0.77** below and right of the mouse: it jumps to it (V+EV, `net`), **0.77** outside the bound: pulled in (V+EV, `net`), **0.77** wider than the bound: past its left edge (V+EV, `net`), **0.80** moved, the cursor shown (V+EV, `net`; interrupted) | ✅ verified | stay, jump, pulled into its bound, wider than its bound; the corner +1 word by word; through interrupts moved then released (181, 141), moved twice and pulled back into its bound, a drag with the cursor SHOWN (priced); through Line-F. 0.89–0.92 with thunks, whole run 0.98–0.99 |
| `0xfe86fa` | `gr_slidebox` (`src/aes/grdrag.c`) | 5 rows (1 INTERRUPTED) + 1 Line-F | 7419 / 106990 across, one pixel of room .. 13868 / 200560 the elevator dragged down | **0.71** at the top, the mouse outside: 0 (V+EV, `net`), **0.71** low, the mouse above it in the track: it jumps up (V+EV, `net`), **0.70** the whole track: no room (V+EV, `net`), **0.70** across, one pixel of room (V+EV, `net`), **0.74** the elevator dragged down (V+EV, `net`; interrupted) | ✅ verified | top, low, no room, one pixel of room, and W_ACTIVE window sliders (the ROM's w_bldactive over W1's window); mul_div only when the room is non-zero; through interrupts the elevator dragged (813, priced); through Line-F. 0.80–0.85 with thunks, whole run 0.95–0.97 |
| `0xfe8bf4` | `rect_change` (`src/aes/mnlib.c`) | 2 rows + 1 Line-F | 404 / 5310 a title's rectangle .. 469 / 6080 an item's rectangle | **0.34** a title's rectangle, **0.39** an item's rectangle | ✅ verified | a title's and an item's rectangle, the flag stored after it (overlap); through Line-F |
| `0xfe8c14` | `do_chg` (`src/aes/mnlib.c`) | 4 rows + 1 Line-F | 34 / 494 a DISABLED item checked for: left alone .. 3046 / 35360 menu_ienable: enabled, redrawn | **0.66** menu_icheck: a check taken off (V, `net`), **0.59** menu_tnormal: a title selected (V, `net`), **0.65** menu_ienable: enabled, redrawn (V, `net`), **0.37** a DISABLED item checked for: left alone (V, `net`) | ✅ verified | every arm: chkdis + DISABLED left alone, set / clear, redrawn / not, the high byte; through Line-F. 0.63–0.68 with thunks, whole run 0.37–0.87 |
| `0xfe8c7a` | `menu_set` (`src/aes/mnlib.c`) | 2 rows + 1 Line-F | 24 / 326 nothing last .. 2198 / 25410 a title selected | **0.23** nothing last (V, `net`), **0.55** a title selected (V, `net`) | ✅ verified | its three arms (nothing last; a title selected); through Line-F. 0.59 with thunks, whole run 0.23–0.82 |
| `0xfe8cb6` | `menu_sr` (`src/aes/mnlib.c`) | 2 rows + 1 Line-F | 14684 / 134174 the Options menu restored .. 14815 / 131968 the File menu saved | **0.58** the File menu saved (V, `net`), **0.58** the Options menu restored (V, `net`) | ✅ verified | save and restore over each of the four menus, the rectangle widened 1 left and 2 right / down (the top untouched); through Line-F. 0.63 with thunks, whole run 0.98 |
| `0xfe8cf4` | `menu_down` (`src/aes/mnlib.c`) | 2 rows + 1 Line-F | 16652 / 178204 the Desk menu dropped .. 73741 / 704894 the Options menu dropped | **0.66** the Desk menu dropped (V, `net`), **0.74** the Options menu dropped (V, `net`) | ✅ verified | titles 3..6 (walks 0..3), a DISABLED title, an item with a CHILD (a G_BOX staged out of the desk's own spare objects 26 / 27 — depth 1 killed); through Line-F. 0.73–0.81 with thunks, whole run 0.93–0.98 |
| `0xfe8d6e` | `mn_do` (`src/aes/mnlib.c`) | 4 rows (1 INTERRUPTED) + 1 Line-F | 4529 / 53488 the button pressed on a title .. 117943 / 1186762 a DISABLED item clicked: nothing chosen, the title put back | **0.53** the mouse moved off the bar (V+EV, `net`), **0.61** the button pressed on a title (V+EV, `net`), **0.61** the button pressed off the bar (V+EV, `net`), **0.63** a DISABLED item clicked: nothing chosen, the title put back (V+EV, `net`; interrupted) | ✅ verified | pass 1's exits (moved off the bar; pressed on a title / off it); each title's drop-down, the bar past the titles and a SELECTED + DISABLED title pinned to the block on the whole image; every LATER pass through interrupts at the door — an item reached and clicked (1, View / 29), a DISABLED item clicked, the menu left (MN_OUT_OF_MENU) and entered again, an item back onto its title, title to title, the title's button toggle, pressed on the title, dragged and released (View / 30), the DISABLED-alone busy loop left by the mouse, an item's child under the mouse, and an interrupt at pass 1's own wait (the door cap 40,000 from its 1,697-instruction nested ev_multi); the worst interrupted shape PRICED (the DISABLED item clicked, three door windows), every returning interrupted case through the bench's second differential; C first in a child (30 s); through Line-F. 0.55–0.69 with thunks, whole run 0.82–0.95 |
| `0xfe902a` | `mn_bar` (`src/aes/mnlib.c`) | 5 rows + 1 Line-F | 310 / 4288 hidden .. 21527 / 235886 shown, the cursor shown | **0.74** shown again after hidden (V+EV, `net`), **0.74** shown, no accessory (V+EV, `net`), **0.72** shown, six accessories (V+EV, `net`), **0.65** hidden (EV, `net`), **0.74** shown, the cursor shown (V+EV, `net`) | ✅ verified | 0 / 1 / 6 accessories, hidden, shown after hidden, over the cursor shown and hidden; the fake click post_button(ctl_pd, 1, 1) through the door; the pid stored as a LONG; no high-resolution case (bar-height-wchar unpinned); through Line-F. 0.75–0.81 with thunks, whole run 0.94–0.96 |
| `0xfe91a4` | `mn_clsda` (`src/aes/mnlib.c`) | 2 rows + 1 Line-F | 24 / 330 no accessory .. 1634 / 20800 two: PD0 and the screen manager | **0.52** no accessory (V, `net`), **0.64** two: PD0 and the screen manager (EV, `net`) | ✅ verified | 0 / 1 / 2 accessories, AC_CLOSE to each through ap_sendmsg (its ap_rdwr through the door); through Line-F |
| `0xfe91e2` | `mn_register` (`src/aes/mnlib.c`) | 4 rows + 1 Line-F | 27 / 388 all six taken .. 220 / 2538 thirteen characters named | **0.73** the running process named (`through`), **0.74** thirteen characters named (`through`), **0.64** an accessory's slot (`through`), **0.41** all six taken (`through`) | ✅ verified | -1 (the running process named; thirteen characters, the most the 14-byte frame holds), slots 0..5, all taken; registered by the ROM's own runs; through Line-F |
| `0xfe5856` | `pd_nameit` (`src/aes/mnlib.c`) | 2 rows + 1 Line-F | 116 / 1356 a program named .. 124 / 1426 eight characters, no extension | **0.87** a program named (`through`), **0.88** eight characters, no extension (`through`) | ✅ verified | a program; eight characters (p_cda whole); NINE (the 9th alone on p_cda's top byte — strscn writes no NUL); through Line-F |
| `0xfe6c98` | `fm_strbrk` (`src/aes/fmlib.c`) | 3 rows + 1 Line-F | 305 / 2962 the shortest alert's message .. 3374 / 30216 the longest alert's message | **0.83** the longest alert's message (`through`), **0.84** the shortest alert's message (`through`), **0.83** a line past the cap (`through`) | ✅ verified | an alert section into the ob_spec strings, read a byte at a time between the stores: every real alert (under fm_parse); '\|' and ']' doubled (itself once — but at the 31-character cap the second stays a delimiter: "\|\|" an empty line, "]]" the end); the cap's skip, its NUL stored before the skip reads (an application's buffer over its own string); a NUL inside (the byte after decides); "a\|]" one more, empty, line; six lines; the signed index; the three answers stored last, index then count then longest; each line's buffer read when the line begins; objects up to 10 byte for byte, and a 5th button or 10th line — object 11, ob_spec `$ff1100`, ABOVE RAM, where the ROM's store is lost — REFUSED BY NAME (the bus accessors' store-above-RAM refusal, in a child), the bound itself pinned (RAM's last bytes stored, the first byte or word past refused); every pointer on the 24-bit bus; through Line-F. POISONED but the 11 direct cases whose inverted in/out index walks above RAM (measured one by one); POISONED under fm_parse. Mutation: fmlib.c's line under fq |
| `0xfe6d84` | `fm_parse` (`src/aes/fmlib.c`) | 2 rows + 1 Line-F | 596 / 6144 the shortest alert, 3834 / 34970 the longest alert | **0.83** the longest alert (`through`), **0.80** the shortest alert (`through`) | ✅ verified | the icon (str[1] - '0', SIGNED; digits 4, 5, 6, 9 and ':' under fm_alert), the lines from object 2 and the buttons from object 7, the longest button counted one more (read back after the store): all 30 alerts of the AES's and the desk's resources; an application's six lines and four buttons (the 4th into AES tree 2's root, its G_BOX colour word `$1143` taken for a string pointer); five buttons and ten lines REFUSED by name where the ROM's store goes above RAM; the buttons read after the lines are written over them; its index a frame local (host slot); through Line-F |
| `0xfe6df8` | `fm_build` (`src/aes/fmlib.c`) | 2 rows + 1 Line-F | 1188 / 14840 the shortest alert, 1878 / 23708 the longest alert | **0.51** the longest alert (`through`), **0.49** the shortest alert (`through`) | ✅ verified | the alert tree laid out in cells (half a cell of pixels in the root's height's high byte), all ten objects unlinked, icon/lines/buttons added, the buttons SELECTABLE\|EXIT and unselected, the last LASTOB too: over every alert's own fm_parse (the ROM's, continued from), no icon, a capped line, six lines and four buttons (past the tree), buttons wider than the lines; its four GRECTs one host slot; through Line-F. `max(nmsg, 1)` and the button row's unsigned halving UNREACHABLE (each needs a 5th button or a 10th line, whose store faults first) |
| `0xfe7214` | `find_obj` (`src/aes/fmlib.c`) | 4 rows + 1 Line-F | 45 / 574 FORWARD, found next .. 358 / 3478 FORWARD, none to the end | **0.47** FORWARD, found next, **0.70** BACKWARD, from the selector's last, **0.69** DEFLT, the desk's longest dialog, **0.70** FORWARD, none to the end | ✅ verified | FORWARD / BACKWARD to an EDITABLE, DEFLT from the root to a DEFAULT, any other `which` the first EDITABLE from object 0 itself; the walk ends at LASTOB (tested after the flag) or below 0, answering `start`: every dialog of both resources from the root, each field and the last object; on the 24-bit bus; through Line-F |
| `0xfe727a` | `fm_inifld` (`src/aes/fmlib.c`) | 2 rows + 1 Line-F | 16 / 230 a field, 90 / 1108 field 0 | **0.24** field 0, **0.25** a field | ✅ verified | the field, or for 0 find_obj(tree, 0, FORWARD): every dialog; 3, -1, $7fff kept; through Line-F |
| `0xfe7298` | `fm_keybd` (`src/aes/fmlib.c`) | 3 rows + 1 Line-F | 39 / 492 a key it does not move by .. 2301 / 24986 Return, the default drawn | **0.65** Return, the default drawn (V, `net`), **0.46** Tab (V, `net`), **0.33** a key it does not move by (V, `net`) | ✅ verified | table `$fefa30` (6 keys and 0, then 7 labels — key 0 and every unmatched key share the 7th): shift-Tab/Up back, Tab/Down on, Return/Enter the default from the root — the key cleared BEFORE the search, the object stored and read back, a default selected and drawn (ob_change, answers 0); over every dialog of both resources; Undo, 'a', 0, Esc and $8f09 (the key sign-extended to the table's longs) left; Return with no DEFAULT goes on with 0; pointers on the bus; through Line-F. 0.68 with thunks, whole run 0.33–0.85 |
| `0xfe50ca` | `dq` (`src/aes/fmlib.c`) | 2 rows + 1 Line-F | 29 / 418 one key, 30 / 432 the front round the ring | **0.46** one key, **0.45** the front round the ring | ✅ verified | the front key of a CDA's queue taken off (count first, then the front on, wrapping at 8, the key read after both): queues the event layer filled (keys typed through the BIOS handler, polled by the ROM's chkkbd + forker), the front at 7 after the ROM's own fq; on the bus; through Line-F |
| `0xfe50f8` | `fq` (`src/aes/fmlib.c`) | 2 rows + 1 Line-F | 17 / 246 an empty queue, 378 / 5268 a full queue | **0.19** a full queue, **0.56** an empty queue | ✅ verified | gl_cda's queue emptied (gl_cda re-read each key): 0, 1, 3 and 8 keys queued by the event layer, the front round the ring; with the keyboard handed to PD1 by the ROM's own ct_chgown, PD0's queue flushed and PD1's left (none or two of its own); through Line-F. UNPOISONED (its loop count inverted is 65,535 dequeues). Mutation over fmlib.c (strict, final code, xdist): 73 — 66 killed, 7 survived: following-unsigned EQUIVALENT; build-no-min and build-row-unsigned UNREACHABLE; fq-cda-once, build-hchar-unsigned, dq-front-unsigned and keybd-key-unsigned-ok EQUIVALENT on every reachable machine |
| `0xfe7346` | `fm_button` (`src/aes/fmdo.c`) | 8 rows + 1 Line-F | 81 / 1152 a field: the form goes on in it .. 3963 / 49886 OK: watched, selected, an exit | **0.62** OK: watched, selected, an exit (V+EV, `net`), **0.56** the TOUCHEXIT arrow (V, `net`), **0.56** the arrow, two clicks (V, `net`), **0.61** a field: the form goes on in it (V, `net`), **0.61** the root: nothing (V, `net`), **0.64** a DISABLED OK: not taken (V, `net`), **0.61** a radio button: its group put down (V+EV, `net`), **0.57** a radio exit button among plain siblings (V+EV, `net`) | ✅ verified | TOUCHEXIT (a double click answers obj\|$8000), SELECTABLE not DISABLED taken — a radio group put down (plain siblings, a plain sibling left SELECTED, a LASTOB radio), any other by gr_watchbox — the rise awaited through the NEW door entry ev_button `$fe68a4`; SELECTED EXIT ends; a field goes on in it; a held radio BLOCKS in ev_button and a held OK in gr_watchbox's wait, each held to the ROM stopped there; frame a host slot; the bus; through Line-F. Its `andi #9` is redundant (SELECTABLE arm). Mutation: fmdo.c's line under bell. 0.59–0.65 with thunks, whole run 0.56–0.90 |
| `0xfe74a4` | `fm_do` (`src/aes/fmdo.c`) | 18 rows (16 INTERRUPTED, 5 of them SLICES of one 38-key session) + 1 Line-F | 4605 / 58116 a 38-key session: the dialog taken, to its first wait .. 78738 / 991374 typed, Left, Delete, Right, Return | **0.67** Return in the ring (V+EV, `net`), **0.70** abc, then Return, in the ring (V+EV, `net`), **0.65** OK clicked, released on it (V+EV, `net`; interrupted), **0.67** off the dialog: the bell, then Return (V+EV, `net`; interrupted), **0.66** the name field clicked, a key typed, Return (V+EV, `net`; interrupted), **0.65** a DISABLED OK clicked, then Return (V+EV, `net`; interrupted), **0.70** typed, Left, Delete, Right, Return (V+EV, `net`; interrupted), **0.67** Tab to the name, typed, Return (V+EV, `net`; interrupted), **0.75** a 37-character path: Backspace, Return (V+EV, `net`; interrupted), **0.75** a 37-character path: a key, Return (V+EV, `net`; interrupted), **0.75** a 37-character path: Left, Delete, Return (V+EV, `net`; interrupted), **0.72** a 37-character path: Escape, Return (V+EV, `net`; interrupted), **0.58** a radio button clicked, then Return (V+EV, `net`; interrupted), **0.67** a 38-key session: the dialog taken, to its first wait (V+EV, `net`; interrupted, sliced), **0.68** a 38-key session: the first key, to a VDI call inside it (V+EV, `net`; interrupted, sliced), **0.76** a 38-key session: the first key, from that VDI call to the next wait (V+EV, `net`; interrupted, sliced), **0.77** a 38-key session: the last character typed (V+EV, `net`; interrupted, sliced), **0.71** a 38-key session: Return, to the return (V+EV, `net`; interrupted, sliced) | ✅ verified | the selector and the desk's dialogs (centred by the ROM's ob_center): keys in the ring and typed one per wait (every move key fm_keybd takes, Backspace/Esc/Left/Right/Delete/Undo into ob_edit), the path field staged as fs_input fills it (37 of its 38 characters), clicks delivered through the ROM's own ISRs (OK, Cancel, a drag off and release, the TOUCHEXIT arrow and a slot, a DOUBLE CLICK, a field, the edited field, off the tree → the bell, a DISABLED OK, a key + a press in one wait — the click's verdict wins), a key queued before (fq), an EDITABLE\|TOUCHEXIT field; nothing delivered → blocks (refused, held to the ROM); a 38-key session (the path field typed full from empty, then Return: 728,664 insns, declared budget 4,000,000) is PRICED BY ITS SLICES, each cut at a wait or at a VDI call and held to the ROM's memory at both ends; the last character typed is the worst, 0.77 (it was 0.75, the long path's rows), and the partition test holds every stretch between its slices at or under it (the review measured the 35 keys between the first and the last: 0.70 rising to 0.77). Frame a host slot; Line-F. 0.61–0.81 with thunks, whole run 0.80–0.95 |
| `0xfe75ec` | `fm_dial` (`src/aes/fmdo.c`) | 8 rows + 1 Line-F | 292 / 4232 FMD_START .. 120570 / 1702378 FMD_GROW | **0.79** FMD_START (V, `net`), **0.84** FMD_GROW (V, `net`), **0.84** FMD_SHRINK (V, `net`), **0.87** FMD_FINISH (V, `net`), **0.77** a type it does not know (V, `net`), **0.77** -1 (V, `net`), **0.75** FMD_FINISH over an open window (V+EV, `net`), **0.61** FMD_FINISH, drawing held (V, `net`) | ✅ verified | every arm, cursor hidden and shown; FINISH over a window (a WM_REDRAW to its owner through ap_sendmsg's door, merged by ap_rdwr) and with drawing HELD (the ROM's wind_set(13)); the D0 form_dial stores MODELLED: the type, gsx_mon's 1/0, or w_clipdraw's held 1. 0.64–0.97 with thunks, whole run 0.80–1.00 |
| `0xfe7002` | `fm_alert` (`src/aes/fmdo.c`) | 6 rows (1 INTERRUPTED) + 1 Line-F | 61844 / 660246 an application's: no icon, one button, Return .. 179063 / 1776364 an application's: five lines at the cap, three buttons, Return | **0.67** the longest alert (AES string 16), Return (V+EV, `net`), **0.61** the shortest alert (AES string 18), Return (V+EV, `net`), **0.60** an application's: no icon, one button, Return (V+EV, `net`), **0.65** an application's: three buttons, Return (V+EV, `net`), **0.68** an application's: five lines at the cap, three buttons, Return (V+EV, `net`), **0.64** the third of three buttons clicked (V+EV, `net`; interrupted) | ✅ verified | all 30 alerts of both resources and an application's (icons 0–3, and 4, 5, 6, 9, ':' past the AES's three BITBLKs; 1–3 buttons; five 31-char lines), defaults 0–4 (none / past the buttons: Return then blocks), a NEGATIVE default (DEFAULT on a message line of the shared tree, answered -1), each button clicked, a key typed into the field-less alert, Tab, a click off it (bell), the cursor hidden and shown; frame a host slot; the bus; Line-F. Over the bench cap and NAMED: five 31-char lines with three 10-character buttons (200,973 ROM insns), priced by its neighbours. Root OUTLINED / ob_draw depth: equivalent mutants. 0.67–0.75 with thunks, whole run 0.93–0.96 |
| `0xfe764c` | `fm_show` (`src/aes/fmdo.c`) | 3 rows + 1 Line-F | 96860 / 975854 Bad Function #, no values (an unimplemented call's) .. 113035 / 1129794 insert disk %S, a name | **0.61** Bad Function #, no values (an unimplemented call's) (V+EV, `net`), **0.62** TOS error #%W, a word (V+EV, `net`), **0.63** insert disk %S, a name (V+EV, `net`) | ✅ verified | rs_str's copy, merged into `$b99a` when handed values (%W, %S), as the alert; the values pointer on the bus; Line-F. 0.67–0.69 with thunks, whole run 0.95 |
| `0xfe768c` | `eralert` (`src/aes/fmdo.c`) | 7 rows + 1 Line-F | 90068 / 913556 error 5, Return .. 166355 / 1634806 error 3, Return | **0.68** error 0, Return (V+EV, `net`), **0.68** error 1, Return (V+EV, `net`), **0.68** error 2, Return (V+EV, `net`), **0.69** error 3, Return (V+EV, `net`), **0.67** error 4, Return (V+EV, `net`), **0.60** error 5, Return (V+EV, `net`), **0.63** error 6, Return (V+EV, `net`) | ✅ verified | errors 0–6 × drives A/B (every line, the drive letter merged where named), Retry by Return (1), Cancel clicked (0), and error 3 answering Retry after a negative default; the tables read in place; its name and the pointer to it a host slot; Line-F. A code past 6 (the critic handler keeps ~error's high byte) is refused by name, unpinnable. 0.67–0.75 with thunks, whole run 0.94–0.96 |
| `0xfe7712` | `fm_error` (`src/aes/fmdo.c`) | 8 rows + 1 Line-F | 24 / 346 code 64: nothing shown .. 151138 / 1480904 code 15, Return | **0.64** code 2, Return (V+EV, `net`), **0.65** code 4, Return (V+EV, `net`), **0.65** code 5, Return (V+EV, `net`), **0.64** code 8, Return (V+EV, `net`), **0.66** code 15, Return (V+EV, `net`), **0.61** code 0, Return (V+EV, `net`), **0.62** code -1, Return (V+EV, `net`), **0.29** code 64: nothing shown (V, `net`) | ✅ verified | codes 2–18 by the table, 0/1/19/63/-1/-32768 "TOS error #" + the word unsigned, >63 nothing (stored nothing), each alert's lines; its `1` answer after an application's form_alert(-1, …) left DEFAULT on a message line (pinned, the machine the ROM's own fm_alert run leaves); its argument word a host slot (merge_str's %W); Line-F. 0.68–0.72 with thunks, whole run 0.29–0.96 |
| `0xfe3a0c` | `bell` (`src/aes/fmdo.c`) | 4 rows + 1 Line-F | 46 / 792 the bell on, the console mid-escape (ESC Y, its row) .. 57 / 900 the bell on | **1.06** the bell on, **1.06** the bell off, **1.07** the bell on, the console mid-escape (ESC), **1.07** the bell on, the console mid-escape (ESC Y, its row) | ✅ verified | BIOS Bconout(CON:, BEL) by `trap #13` on target (bcon.h's constant shape), the BIOS core off it; conterm's bell bit on (the sound list planted) and off, the console mid-escape (ESC, ESC Y row and column, ESC b); `savptr` in the stack band (the trap's save). Its 1.07 excess is the d2/a2 save round `trap #13` under GCC's ABI (the ROM leaf saves nothing): a floor, not a C spelling. Mutation over fmdo.c + evdoor.h (strict, xdist): 108 — 104 killed, 4 equivalent (r-all-taken, d-init-no-clear, a-no-outline, a-shallow) |
| `0xfe7782` | `fs_start` (`src/aes/fslib.c`) | 1 row + 1 Line-F | 235 / 3628 the selector's tree, centred | **0.59** the selector's tree, centred (`through`) | ✅ verified | rs_gaddr(R_TREE, 0) of the AES's own resource into ad_fstree `$972a`, ob_center into gl_rfs `$9c00`; over the snapshot, both staged stale, the root moved off-centre first; through Line-F |
| `0xfe77ae` | `fs_back` (`src/aes/fslib.c`) | 3 rows + 1 Line-F | 58 / 674 a folder's path, from its end .. 585 / 5486 a path of 79 characters with no separator: the longest the selector holds | **1.04** a path of 79 characters with no separator: the longest the selector holds (`through`), **0.66** a drive and a spec: the separator put in (`through`), **0.64** a folder's path, from its end (`through`) | ✅ verified | back from `end` to a `:` or `\` or to the path (the two pointers compared whole: a top byte on one alone walks on below the path); on a `:` a `\` inserted after it by ins_char in 64 bytes of room — a tail of 63 or more is CUT by its NUL, pinned at 62/63/64/70; nothing read below the path; both pointers on the bus; the ROM's own first calls from fs_input for four paths. The 1.04 is the per-byte scan, 70 cycles against 64 (1.094 at the limit): the row is the longest path the selector holds, 79 characters (the path field's text is 80 bytes: fs_sset has no bound, and a longer path runs on over the selection field's); 120 characters measure 1.059, 250 measure 1.077 |
| `0xfe77ee` | `fs_pspec` (`src/aes/fslib.c`) | 2 rows + 1 Line-F | 100 / 1202 a folder's path .. 659 / 6410 a path of 79 characters with no separator: the longest the selector holds | **0.96** a path of 79 characters with no separator: the longest the selector holds (`through`), **0.39** a folder's path (`through`) | ✅ verified | fs_back, then past its `\`; with none the caller's path becomes the ROM's `"A:\*.*"` (`$fefafc`, always drive A) and the spec is path + 3, the path's top byte kept; an empty spec, a drive and a spec; as fs_input first calls it. The 0.96 is fs_back's scan (250 characters measure 1.045) |
| `0xfe7826` | `fs_active` (`src/aes/fslib.c`) | 6 rows + 1 Line-F | 874 / 12102 a missing folder .. 154325 / 1563128 a hundred names of eight characters and three: the bell | **0.83** a hundred names of eight characters and three: the bell (V, `net`), **0.83** a missing folder (V, `net`), **0.81** an empty folder (V, `net`), **0.80** nine names (V, `net`), **0.79** a hundred names: the bell (V, `net`), **0.74** the root: its folders and three files (V, `net`) | ✅ verified | busy form; Fsetdta; Fsfirst(path, 16) / Fsnext: `.` entries skipped, DTA+29 marked 7 folder / space file by the SUBDIR BIT alone (`btst #4`: a read-only `$11` and an archived `$30` folder are folders, whatever the spec), every folder and each file wildcmp(spec) keeps copied kind + name into the names block, its offset a LONG in the index; at 100 names KEPT (101 files under `F?0?.DAT` are read to their end, eleven kept, no bell) one more Fsnext, then Cconout(BEL) — also for exactly 100; the count stored BEFORE the sort (laid over the index, a name and the names pointer); shell sort through the two scratches, equal names left in place; arrow form. Machines the ROM's own fs_input stopped at its entry, over a staged disk of thirteen directories (0, 1, 9, 10, 99, 100, 101 names; sorted, reversed, shuffled; folders among files; a name held three times) and four more disks, each the first plus ONE folder (so no machine over the first moves), REAL GEMDOS on both shores: thirteen specs, a missing folder, B:, C:, no separator, uncleared blocks, the cursor shown, the busy form at the first GEMDOS call. Priced over GEMDOS REPLAYED (the ROM's own answers and DTAs, derived call by call; the ledger pins every frame), which leaves what the disk's run leaves. 0.94 with thunks (a hundred names of eight characters and three: the bell); a hundred full-length names SHUFFLED are past the bench cap (sixty and eighty measure 0.816 / 0.815). UNPOISONED. Mutation over fslib.c's event-free half + the glue (strict, final code, xdist, a control every fifteen): 239 — 231 killed, 8 survived, 0 abnormal: act-kind-not-reread, act-bell-first, el-stores-swapped and fmt-no-min EQUIVALENT; act-dta-not-reread and fmt-kind-first EQUIVALENT ON EVERY REACHABLE MACHINE (the second differs only for a name of 72 bytes or more, which no directory gives); fmt-answers-swapped and snext-with-a-word UNOBSERVABLE (a frame nothing reads; a trap frame's length the host cannot see). snext-function is killed on its targeted run and ABNORMAL in its full run (the host's Fsfirst spins over real GEMDOS) |
| `0xfe79fe` | `fs_1scroll` (`src/aes/fslib.c`) | 2 rows + 1 Line-F | 38 / 476 down .. 40 / 486 up at the top | **0.42** up at the top, **0.36** down | ✅ verified | top - 1 for the up arrow (8), + 1 for any other, kept in 0 .. count - 9, the top itself when count <= 9; 15 tops x 6 arrows x 10 counts incl. -32768 / 32767 (the word difference signed) and an arrow of `$0108` (the arrow is a WORD: down) |
| `0xfe7a44` | `fs_format` (`src/aes/fslib.c`) | 3 rows + 1 Line-F | 756 / 10126 an empty list .. 2298 / 26546 a hundred names, the first nine | **0.88** a hundred names, the first nine (`through`), **0.86** folders and files (`through`), **0.76** an empty list (`through`) | ✅ verified | nine rows from name `top`: kind + the 8.3 name by fmt_str, a space past the names; each row's text set (fs_sset) THEN its state cleared; the elevator sized AFTER the rows: the rows' share of the track by mul_div, at least gl_hbox / 2, placed by mul_div. Every list shape and page (the other pages measure 0.876-0.878); tops and counts off the list; `count - top` a word that wraps; row + top a LONGWORD sum; both orders by a row's text laid over its own state and over the slider's height; nine names take no share (a child first: the mutant divides by 0). The half-box floor binds for no directory of <= 100 names (pinned by a count of 200) |
| `0xfe7b70` | `fs_sel` (`src/aes/fslib.c`) | 3 rows + 1 Line-F | 15 / 218 row 0: none .. 4668 / 50790 a row selected, the cursor shown | **0.65** a row selected, the cursor shown (V, `net`), **0.63** a row selected (V, `net`), **0.20** row 0: none (V, `net`) | ✅ verified | row != 0 (a WORD: `$0100` is a row): ob_change(ad_fstree, row + 11, state, drawn); rows 1..9, deselect, the state it has, rows -1 and 10, the tree read from ad_fstree (an application's copy); as fs_input first calls it (row 0). 0.70 with thunks (a row selected, the cursor shown) |
| `0xfe7b92` | `fs_nscroll` (`src/aes/fslib.c`) | 6 rows + 1 Line-F | 90 / 1142 up at the top: nothing moves .. 192598 / 2113542 a page down, the cursor shown | **0.80** eight rows down, the cursor shown: one row copied (V, `net`), **0.79** a page down, the cursor shown (V, `net`), **0.79** a page down: the whole list drawn (V, `net`), **0.78** one row down, the cursor shown (V, `net`), **0.78** one row down (V, `net`), **0.39** up at the top: nothing moves (V, `net`) | ✅ verified | n x fs_1scroll, each from the last; moved: the selected row deselected and forgotten, fs_format from the new top, the rows that stay copied by bb_screen (up or down; nine or more: none), the new rows drawn under their own clip, the slider under the caller's, which is put back; not moved: nothing stored. 20 scrolls over 5 directories, a selected row, a narrowed clip, pointers on the bus. 0.90 with thunks (eight rows down, the cursor shown: one row copied). The page rows run 188,640 and 192,598 instructions, 4-6% under the bench cap |
| `0xfe7cfa` | `fs_newdir` (`src/aes/fslib.c`) | 4 rows + 1 Line-F | 156450 / 1555322 an empty folder .. 198776 / 1999354 thirty-four names of eight characters and three | **0.82** thirty-four names of eight characters and three (V, `net`), **0.81** an empty folder (V, `net`), **0.79** twenty-eight names in no order (V, `net`), **0.79** the root (V, `net`) | ✅ verified | the path field drawn; fs_active; fs_format from 0; the title " spec " built in the `$9afe` scratch and copied out; objects 5, 6, 7 drawn from the ROM's list `$fefaac`. Nine paths as fs_input first calls it, the cursor shown, pointers on the bus. A ROM DEFECT reproduced: the title has no bound — a spec of 40 characters writes over gl_mntree, of 50 over gl_rzero (five cases, byte for byte). 0.93 with thunks (thirty-four names of eight characters and three). Thirty-four full-length names are the most under the bench cap (198,776; a hundred run 274,097 over the replay): past them Tier 1 only, the read and the sort priced by fs_active's own rows |
| `0xfe7d90` | `fs_input` (90, fsel_input, `src/aes/fslib.c`) | 37 rows (34 SLICES of six sessions) + 1 Line-F | 78 / 1164 no memory: the names refused .. 195098 / 2131800 a drag, a page, the title, Cancel: the track clicked: a page scrolled | **0.96** a root with no drive: the close box's arm alone, from the form's end: the scan, to its directory's read (V+EV, `net`; interrupted, sliced), **0.88** a spec that fills the title's scratch: the selector put away: the strings handed back, the screen given back, the blocks freed (V+EV, `net`; interrupted, sliced), **0.88** a spec typed, a row: the selector put away: the strings handed back, the screen given back, the blocks freed (V+EV, `net`; interrupted, sliced), **0.88** a hundred names: the selector put away: the strings handed back, the screen given back, the blocks freed (V+EV, `net`; interrupted, sliced), **0.88** a drag, a page, the title, Cancel: the selector put away: the strings handed back, the screen given back, the blocks freed (V+EV, `net`; interrupted, sliced), **0.88** rows, a scroll, a folder, the close box, Return: the selector put away: the strings handed back, the screen given back, the blocks freed (V+EV, `net`; interrupted, sliced), **0.88** a root with no drive: the selector put away: the strings handed back, the screen given back, the blocks freed (V+EV, `net`; interrupted, sliced), **0.85** a root with no drive: the close box: fs_back's scan below the path's buffer, to its directory's read (V+EV, `net`; interrupted, sliced), **0.84** a spec typed, a row: its directory read: thirteen files (V+EV, `net`; interrupted, sliced), **0.83** a hundred names: its directory read: a hundred names, the bell (V+EV, `net`; interrupted, sliced), **0.82** a drag, a page, the title, Cancel: the elevator dragged: a move (V+EV, `net`; interrupted, sliced), **0.82** a spec typed, a row: the list formatted and drawn (V+EV, `net`; interrupted, sliced), **0.81** a spec that fills the title's scratch: the selector drawn over a path of 46 characters, to its directory's read (V+EV, `net`; interrupted, sliced), **0.81** rows, a scroll, a folder, the close box, Return: an empty list formatted and drawn (V+EV, `net`; interrupted, sliced), **0.81** a spec typed, a row: the selector drawn, to its directory's read (V+EV, `net`; interrupted, sliced), **0.80** a spec typed, a row: the new spec's names read, listed, the row selected (V+EV, `net`; interrupted, sliced), **0.79** rows, a scroll, a folder, the close box, Return: an empty folder read (V+EV, `net`; interrupted, sliced), **0.79** a drag, a page, the title, Cancel: the list scrolled to where it was dragged: ten rows (V+EV, `net`; interrupted, sliced), **0.78** a drag, a page, the title, Cancel: the track clicked: a page scrolled (V+EV, `net`; interrupted, sliced), **0.78** a drag, a page, the title, Cancel: the elevator let go: the screen given back (V+EV, `net`; interrupted, sliced), **0.78** a hundred names: the list sorted (V+EV, `net`; interrupted, sliced), **0.77** the DTA refused: the names and the index freed (V, `net`), **0.76** the index refused: the names freed (V, `net`), **0.73** no memory: the names refused (V, `net`), **0.73** rows, a scroll, a folder, the close box, Return: the down arrow: the list scrolled a row (V+EV, `net`; interrupted, sliced), **0.70** a spec that fills the title's scratch: a row clicked whose kind is the title's overrun: the path made, to its directory's read (V+EV, `net`; interrupted, sliced), **0.70** a drag, a page, the title, Cancel: the title clicked: to its directory's read (V+EV, `net`; interrupted, sliced), **0.69** rows, a scroll, a folder, the close box, Return: the close box: the path cut, to its directory's read (V+EV, `net`; interrupted, sliced), **0.68** a spec typed, a row: the path edited, a row clicked: to its directory's read (V+EV, `net`; interrupted, sliced), **0.67** rows, a scroll, a folder, the close box, Return: a folder's row clicked: the path made, to its directory's read (V+EV, `net`; interrupted, sliced), **0.66** rows, a scroll, a folder, the close box, Return: Return: to the form's end (V+EV, `net`; interrupted, sliced), **0.66** rows, a scroll, a folder, the close box, Return: the same row clicked again (V+EV, `net`; interrupted, sliced), **0.65** rows, a scroll, a folder, the close box, Return: another row clicked: the first put down (V+EV, `net`; interrupted, sliced), **0.65** rows, a scroll, a folder, the close box, Return: the form taken, to its first wait (V+EV, `net`; interrupted, sliced), **0.65** rows, a scroll, a folder, the close box, Return: a file's row clicked: selected, its name the selection (V+EV, `net`; interrupted, sliced), **0.63** a drag, a page, the title, Cancel: Cancel clicked: to the form's end (V+EV, `net`; interrupted, sliced), **0.62** a drag, a page, the title, Cancel: the elevator pressed: the screen taken, to the drag's first wait (V+EV, `net`; interrupted, sliced) | ✅ verified | the file selector run whole: three dos_alloc (a refusal: those before freed, 0), the fields set, fm_dial, the first draw at depth 1; each pass fm_do, the path compared with the one last read ($bb3e) and read when it differs (GEMDOS's spec always `*.*`), the switch `$fefab0` on the object; the strings handed back, *button = inf_what (neither: 0), three dos_free. 80 whole SESSIONS, every interrupt the ROM's own ISR's at a wait, GEMDOS REPLAYED from the ROM's own run of the same session over the staged disk (each replayed run held to the real disk's where the selector can see it): every row of the table but object 7's (its children tile it: no click answers it), each exit, the path edited before each, twelve paths, a hundred names; the read's own order (a row selected, the path edited, Return / OK: the row put down, THEN the button); the top 0 from the read on, in the pass that reads (a page, the path edited, an arrow / the elevator). 20 sessions cut short at a wait (the C refused where the ROM blocks, its image the ROM's there: the selector on the screen); every VDI call of each session held to the ROM's in order, AND WHAT THE SELECTOR HOLDS AS EACH IS MADE (its tree, its fields' and rows' texts, its scratches, the two paths: a tree word set and put back between two waits is seen); real GEMDOS on both shores for keys typed ahead and the three no-memory arms (the arena exhausted by the ROM's own Malloc) with the glue's parked addresses held at every call. ROM DEFECTS reproduced: an edited path + Return reads the directory then answers CANCEL (handing back a selected row's name all the same); the close box over `\*.*` scans below the path's buffer (through the AES's four text buffers into the ORECT pool) and overwrites five bytes of AES data; a stale length puts a second `\` after the drive; a spec past 25 characters runs the title over the first row's text, whose kind is then no space — the row is taken for a FOLDER. `fs_input("")` NEVER RETURNS (the same memory at consecutive passes), and neither does the close box over `\*.*` once a formatted text of 77+ characters was drawn (AES_FMTSTR's tail lies under the path): both refused by name off target, the image the ROM's at that pass. Priced by its slices, cut at door calls, GEMDOS calls and one VDI call. WORST 0.96 (own 0.9553; 1.00 with thunks (a root with no drive: the close box's arm alone, from the form's end: the scan, to its directory's read)): the close box's arm over a root with no drive, cut ALONE from fm_do's end — the ROM's defect scan, 849 bytes, by fs_back CALLED as the ROM calls it there (`fs_back_called`, both of the close box's sites: 78 cycles a byte against the ROM's 64; inlined it was 114, and the arm 1.20 / 1.25 with thunks behind a wait-cut row of 1.03); the same click cut from the wait is 0.85 (0.90). Then the put-away, 0.88 in every session (0.98 with thunks). Frame a host slot; Line-F. Mutation (strict, final code, a control every fifteen): 224 — 217 killed, 7 survived, 0 abnormal: show-tree-before-allocs, pass-length-unsigned, drag-zero-is-down, row-old-put-down-when-none and row-reselected-when-same EQUIVALENT; read-any-put-down EQUIVALENT ON EVERY STAGED MACHINE; row-buttons-are-rows UNREACHABLE (row-folder-is-file, once called equivalent, is KILLED by the long spec's session). Coverage (llvm-cov, an -O0 build of the final code, the three batteries' 492 tests): fslib.c 407 of 410 lines (99.27 %), 132 of 134 branches (98.51 %) — the misses are the host refusal's taken arm (it runs in a child that aborts: no profile is written; its words are asserted) and act_on_the_object's dead upper bound (`object <= FS_LAST_NAME` is never false past a row) |
| `0xfe3a46` | `dos_snext` (`src/aes/gemdosif.c`) | 2 rows + 1 Line-F | 133 / 1604 found .. 138 / 1652 no more files | **1.01** found, **1.01** no more files | ✅ verified | Fsnext by its own `bsr __DOS`, then dos_sfirst's tail `$fe3a2c` (NOT `$fe3c28`): 1 when the answer's WORD is 0; ENMFIL or EFILNF -> DOS_AX 18. Real GEMDOS: found, and ENMFIL by a chained run; the replay: eight answers no disk gives (a zero word under a set high word is found; under a negative long, found and failed) |
| `0xfe3bf6` | Cconout glue (`src/aes/gemdosif.c`) | 12 direct/Line-F | — | unpriced — a HOST ARGUMENT (its caller's return site, parked through `$fe3c28`; dos_sdta's precedent) | ⚠️ verified, unpriced | Cconout of the word its caller pushed: real GEMDOS (BEL rings the BIOS's bell, a letter does not, a word whose low byte is BEL does), and the replay (one word under the function, the verdict of 0, the BIOS's own answer and an error); priced inside fs_active's rows that ring it. dos_free, dos_sdta, dos_close and this one now share two helpers, one per frame shape (the target objects of the first three byte-identical) |
| `0xfe4e5a` | `tak_flag` (`src/aes/evsync.c`) | 3 rows (Line-F: 2 Tier 1 cases, no registered row) | 27 / 404 the caller's own: taken again .. 30 / 412 another process's: refused | **0.59** free: taken, **0.59** the caller's own: taken again, **0.59** another process's: refused | ✅ verified | THE FIRST REBOUND DOOR ENTRY: `evdoor_tak_flag` calls it on both builds. Every lock state the scheduler's own: free; held once / twice; held WITH A PROCESS QUEUED ON IT (the screen manager parked on the lock: SPB_WAIT left alone — the one real state whose wait list is not empty); another process's (PD0 parked holding it, the screen manager woken); released once too often. The owner compared as a long; the count stored before rlr is read (a semaphore laid over rlr). D0's high word on a refusal is the owner's (`clr.w d0`): the answer is a word. Its C first in a fork of the worker (a twin that spun fails its case, never hangs the suite). Unpinned: a REFUSAL with a process already queued (needs a third process — wave 1's amutex battery); equivalent: rlr's second load for the store. Shadowed at every door call of it while the flip is in flight — which names where a red is, and covers nothing more: the twin is held by THIS battery (of 22 real mutants of it, five that are not equivalent pass every door case of seven routines, shadow on or off; this battery kills all five) |
| `0xfe3f5e` | `signal` (`src/aes/evasync.c`) | 4 rows + 1 Line-F | 40 / 536 the running process's own event .. 47 / 652 woken from behind another | **0.77** a process woken from behind another on the not-ready list, **0.72** a process woken, first on the not-ready list, **0.66** a process already woken, **0.65** the running process's own event | ✅ verified | an EVB's event posted to its process, and a parked process made ready and moved to the head of the woken list: every one of the ROM's own 25 calls in 20 scenarios (the dispatcher's loop taking a key, a press, a mouse move, ticks; a message sent; the lock released), each at the machine the ROM makes the call on — first, second and (a staged application, Tier 1) between two others on the not-ready list, already woken, the running process's own, inside forker (rlr −1), onto a woken list holding one. Its evwait test, false on no reachable machine, pinned by a FREE EVB handed directly; its rlr test REDUNDANT (the running process is never parked). On the bus; through Line-F (`$f724`). POISONED where it wakes nobody; UNPOISONED where it wakes (the pass follows inverted links off RAM, measured per case) |
| `0xfe3fba` | `azombie` (`src/aes/evasync.c`) | 3 rows + 1 Line-F | 81 / 1114 the running process's own wait .. 88 / 1230 woken from behind another | **0.63** a wait of a process woken from behind another, **0.60** a parked process's wait, the completed list holding one, **0.56** the running process's own wait | ✅ verified | an EVB onto the head of the COMPLETED list (`$c84a`, `AES_ZOMBIE_LIST` — the map's "timer list" is this), its flag the word 2 whatever it held (0, NOCANCEL 1, a delay's 4, a mouse-leave 8), signal: 25 calls of the ROM's; the list empty and holding one; completed twice (it links to itself); the pointer stored top byte and all; through Line-F (`$f804`). UNPOISONED (measured) |
| `0xfe4002` | `get_evb` (`src/aes/evasync.c`) | 1 row + 1 Line-F | 104 / 1156 | **0.83** an EVB that held a wait (`through`: bfill ships as its `.S`) | ✅ verified | the free list's first EVB taken and its 28 bytes cleared: 31 calls of the ROM's iasync, 12 down to 7 free, EVBs that held a wait; through Line-F (`$f748`). Its EMPTY arm (D0 0, which iasync never tests) UNPINNED: three processes hold at most 10 of the 15. UNPOISONED (measured) |
| `0xfe4030` | `evinsert` (`src/aes/evasync.c`) | 2 rows + 1 Line-F | 30 / 468 onto an empty list, 31 / 482 onto one that holds one | **0.50** onto a wait list that holds one, **0.48** onto an empty wait list | ✅ verified | an EVB at the HEAD of a wait list, its predecessor the head's stand-in (head − `$97f6`'s 4): 22 calls — a CDA's keyboard, button and mouse waits, a PD's pipe readers, a second rectangle onto the first's list (last in, first found); the list's first read before any store (a list laid over the EVB's own field, handed directly — the ONE re-read of the file pinned by an alias; four others are unpinned, alias-only: leave_list's two links, azombie's `$c84a`, get_evb's free-list head, evinsert's second and third stores); on the bus; through Line-F (`$f808`). UNPOISONED (measured) |
| `0xfe4062` | `takeoff` (`src/aes/evasync.c`) | 3 rows + 1 Line-F | 27 / 442 the only wait on its list, 31 / 510 a wait with one after it | **0.63** a wait with one after it, **0.60** the only wait on its list, **0.60** a delay with none after it | ✅ verified | an EVB whose event did not come off its wait list and freed: 24 calls of acancel's — alone, with one after it (its own parameter not handed on), a delay alone; a delay with one after it hands it its ticks (10 + 20 → 30) and a delay behind another hands nothing on — over A STAGED APPLICATION (two delays need a third process), Tier 1 only; on the bus; through Line-F (`$f764`). POISONED, every case |
| `0xfe41bc` | `apret` (`src/aes/evasync.c`) | 2 rows + 1 Line-F | 63 / 906 a key's wait, 74 / 1000 behind another on both lists | **0.79** a wait behind another on both lists, **0.76** a key's wait, alone on both lists | ✅ verified | the running process's completed EVB of one event freed and answered: 22 calls of ev_multi's tail and ev_block — in every one the EVB is the LAST on its process's list (alone, or behind another: ev_multi's aprets take the deepest first), and head / behind another / head with one behind on the completed list; the bit cleared in all three event words, the answer's low word in D0 and its HIGH word in `$c792` (the buttons for a button wait; for a mouse wait its rectangle's WIDTH — the ROM's quirk, pinned). Handed directly over ev_multi's own machine at its acancel, labelled: a completed wait with ANOTHER BEHIND IT on the process's list (the unlink stores a non-zero link: `$fe4226`, which no ROM call shows), and the two answers no caller reaches — no such EVB 100, a pending one 101, two masks ORed 100 (matched whole), nothing stored. Through Line-F (`$f7e4`). UNPOISONED (measured) |
| `0xfe427a` | `acancel` (`src/aes/evasync.c`) | 3 rows + 1 Line-F | 56 / 682 both kept .. 351 / 4638 five cancelled | **0.78** both waits completed and kept, **0.69** one completed wait kept, two cancelled, **0.68** one completed wait kept, five cancelled | ✅ verified | every EVB of the running process among a mask: a completed one kept and answered, any other off the process's list, taken off its wait list and freed, its bit cleared in PD_EVBITS and PD_EVWAIT (PD_EVFLG left): 17 calls of ev_multi's — none to five cancelled, one and two kept, the kept one first, middle and last; its mask filter (false for no caller: ev_multi hands every mask it queued) pinned by masks handed directly. Its NOCANCEL bit alone UNPINNED (azombie overwrites it in the call that sets it). Through Line-F (`$f7f8`). UNPOISONED (measured) |
| `0xfe511a` | `evremove` (`src/aes/evasync.c`) | 3 rows + 1 Line-F | 132 / 1854 a key's wait .. 140 / 1926 a mouse wait | **0.57** a mouse wait, its process woken from behind another, **0.55** a double-click wait counted down, **0.53** a key's wait | ✅ verified | an EVB whose event came: its answer ORed in (an unsigned word), off its wait list, azombie — and the pending multi-click waits (`$c84e`) counted down, never below 1, when (parm >> 16 & `$ff`) > 1: 21 calls of post_keybd / post_button / post_mouse / tchange — keys, single and double clicks, mouse waits alone, ahead of and behind another on the mouse wait, a delay (its parameter cleared by tchange first). ROM QUIRK pinned: no kind is tested, so a mouse wait at x 150 counts a double-click wait down, and one at x 257 (low byte 1) does not. On the bus; through Line-F (`$f7fc`). UNPOISONED (measured). Each C of the eight runs first in a fork of the worker. Mutation over evasync.c + evasync.h + the two aes.h fields (strict, final code, the whole battery): 129 — 114 killed, 15 survived, 0 abnormal: the author's 117 as before, 110 killed / 7 survived (4 EQUIVALENT: elinkoff a constant, signal's rlr test, signal's mask read order, `$c84e` unsigned; 1 EQUIVALENT on every reachable machine: acancel clearing PD_EVFLG too; 2 UNREACHABLE: get_evb's empty list, NOCANCEL alone) — with the case over the lever's poked machine DROPPED, no kill lost; the review's 12: 4 killed (apret's unlink ending the list, by the new labelled case; takeoff's ticks a word; signal's test on the new event alone; apret's high word from its answer), 4 survive ALIAS-ONLY (the four unpinned re-reads), 4 are no-ops by construction |
| `0xfe56f6` | `pd_match` (`src/aes/pdpipe.c`) | 3 rows + 1 Line-F | 31 / 416 by id .. 123 / 1526 by name, the screen manager's | **0.79** by name, the screen manager's (`through`), **0.74** by name, another's first character (`through`), **0.40** by id (`through`) | ✅ verified | by name against an 8-byte copy ended in its frame (one short / one long / first and last character / none; the PD's own name bytes), by id as a WHOLE WORD (`$100` is not the shell; the spare PD's stale 0); on the bus; through Line-F. On a STAGED APPLICATION (Tier 1): a PD whose 9th name character sits on its CDA's top byte still matches by its eight |
| `0xfe5750` | `fpdnm` (`src/aes/pdpipe.c`) | 4 rows + 1 Line-F | 81 / 1112 by id, the shell .. 377 / 4950 by name, none | **0.29** by id, the shell (`through`), **0.19** by id, none (`through`), **0.56** by name, the screen manager (`through`), **0.54** by name, none (`through`) | ✅ verified | the two processes of the snapshot by id and by name, none; the THIRD static PD through a staged application (Tier 1); on the bus; through Line-F. UNPINNED: the accessories' loop (`$c6b2[]`, band 5) |
| `0xfe57e0` | `getpd` (`src/aes/pdpipe.c`) | 1 row + 1 Line-F | 42 / 656 | **0.72** the spare static PD (`through`) | ✅ verified | the spare static PD numbered, `$c680` counted, its UDA marked. On a STAGED APPLICATION's machine (Tier 1; all three static PDs handed out, no accessory): the ROM takes address 0 for a PD — the host's bus accessor refuses the store above RAM by name (a child), having stored what the ROM stores before it. UNPINNED: an accessory's PD (band 5) |
| `0xfe3970` | `uda_insuper` (`src/aes/pdpipe.c`, ships `src/aes/pdpipe.S`) | 1 row + 3 `.S` + 1 Line-F | 4 / 84 | **1.50** the spare UDA (T); `.S` **1.00** ×3 | ✅ verified | hand 68000: three UDAs, on the bus; the C's floor is the image pointer |
| `0xfe397a` | `psetup` (`src/aes/pdpipe.c`, ships `src/aes/pdpipe.S`) | 1 row + 2 `.S` | 12 / 224 | **1.24** the spare PD (T); `.S` **1.00** ×2 | ✅ verified | hand 68000: the rte frame (PC under SR `$2000`) on the stack the PD's UDA saved, the pointer stored back whole; a second frame under the first (a staged application, Tier 1); through Line-F; its SR save word `$8998` dropped by name for the C (`aes_event.SR_PSETUP_DROP`: the caller's CCR), COMPARED by the `.S` rows. Steered: runs without the attribution pass (the saved SP inverted is odd), by name per case |
| `0xfe5886` | `pstart` (`src/aes/pdpipe.c`) | 1 row | 235 / 3046 | **0.76** a program's file (`through`) | ✅ verified | getpd, ldaddr, pd_nameit, psetup, ready, at the HEAD of the woken list (in front of a PD already woken; `onto_the_woken_list`, shared with signal); names with and without a dot, tags; through Line-F; `clr.w p_stat` on a spare PD the ROM's own pipe overrun left waiting; `$8998` dropped by name |
| `0xfe58c0` | `doq` (`src/aes/pdpipe.c`) | 7 rows + 1 Line-F | 103 / 1242 a read of the only message .. 465 / 4474 a read from a full pipe | **0.89** a write into an empty pipe (`through`), **0.89** a write behind seven (`through`), **0.97** a redraw merged into the seventh queued (`through`), **0.96** a redraw none of seven merges with (`through`), **0.94** a read of the only message (`through`), **0.97** a read from a full pipe (`through`), **0.98** a read of a whole full pipe (`through`) | ✅ verified | writes behind 0..7, 32 bytes; WM_REDRAW merged into the first queued for its window (the walk crossing others, a long message stepped over whole, the step a whole word), appended otherwise; reads from the head with the rest moved down, a whole pipe at once; the buffer over the pipe, over the QPB (the count read once), over the PD's own queue pointer (read again); on the bus; through Line-F. On machines the ROM makes past its invariants (its own pipe overrun, a negative index): written through `p_qaddr`, read back at `pd + 56`, the index a signed word read again. The worst row is the longest copy (the C's saving is a constant ~116 cycles: 23 candidates priced, 0.84–0.98). Refused by name: a read past the pipe (the ROM moves 64 KB of GEMBSS, its Line-F handler's copy with it — it returns on 32/40/48 bytes only, through the moved handler). ROM DEFECT pinned on every shore: an odd index is an address error at `$fe5906` |
| `0xfe5988` | `aqueue` (`src/aes/pdpipe.c`) | 6 rows + 1 Line-F | 179 / 2438 a read queued on an empty pipe .. 939 / 10588 a read that frees the waiting writer | **0.59** a write with room (`through`), **0.41** a write queued on a full pipe (`through`), **0.64** a write served to the waiting reader (`through`), **0.59** a read (`through`), **0.39** a read queued on an empty pipe (`through`), **0.74** a read that frees the waiting writer (`through`) | ✅ verified | over the EVB the ROM's iasync hands it: served or queued by the room / the data (five edges; signed words: a negative count is room, a negative index no data), the other end's list chosen by `writing XOR ready` on whole words BEFORE the write, its first wait served at once (PD1 → PD0 parked; a writer parked on the full pipe; a write that fills the pipe); NOCANCEL read by the served write itself; the buffer over the EVB (order); on the bus; through Line-F. On a STAGED APPLICATION (Tier 1): two waiters on one list (the last queued served first) and a third process's reader. ROM DEFECT pinned: a waiting writer served unchecked overruns the pipe into the next PDs (32 bytes; 232 bytes rewriting PD1 and PD2's head). Refused by name: a pid no PD has (2, `$100`). Five cases run with the attribution pass; the rest are steered, by name per case |
| `0xfe65da` | `ap_find` (`src/aes/pdpipe.c`) | 2 rows + 1 Line-F | 377 / 4762 the screen manager .. 464 / 5946 none of that name | **0.60** the screen manager (`through`), **0.57** none of that name (`through`) | ✅ verified | found, eight blanks (the shell), none, unpadded, 9, 10 and ELEVEN characters (the copy over the top two bytes of the caller's saved A6 — the ROM's own boundary, measured through its trap door on the PD's UDA stack: `appl_find("CONTROL.ACC")` answers -1); on the bus; through Line-F; a third process (a staged application, Tier 1); 12+ refused by name where the ROM never returns. PREMISE: the caller's frame below 64 KB (the three static UDAs); an accessory's caller is band 5's |

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
* **Wave 9 band 4 (2026-09-26) — the LAST of GEMDOS: `Frename`, the dispatcher's three arms, `Pexec`'s loader.** Three agents:
  `src/gemdos/fs_rename.c` (`Frename` $fc7af0), `src/gemdos/dispatch.c` (the REDIRECTED arms `$fd328a`, the DEVICE arm
  `$fc99bc`, the DEVICE-NAME arm `$fc9aca`, and the media-change helpers `$fc93f4`/`$fc9468` standalone — which unblocked the
  dispatched `Fopen`/`Fcreate` slices), `src/gemdos/pexec_load.c` (the loader and relocator `$fc85ea` with `$fc4b7c`'s clear,
  `Pexec` modes 0 and 3 end to end over synthesised PRGs). FINDINGS: a cross-directory `Frename` MOVES the entry (`$e5`, then
  `Fcreate` and a 10-byte tail copy — no FAT traffic) and never checks `Fcreate`'s answer, so a refusal reads a basepage byte as a
  handle and the file silently loses its name; its new-name check cannot see hidden/system/directory entries (duplicates);
  redirected `Cconout` writes the byte at `(char<<16)|$7ef4`, redirected `Cconrs` reads its maximum SIGNED (a buffer overrun),
  redirected `Cconin` ignores Fread's answer, `$fc9468` compares against the caller's A4 and never its argument; the loader
  takes `Fopen`'s mode from the high half of the CALLER'S D5, checks no `Fread`, bounds relocation only at chunk edges, leaves
  the file open on every error, and a failed `Pexec(3)` leaks its blocks to the caller. REVIEW (3 finders; C faithful to the asm)
  found: a HOST out-of-bounds read (the broken Cconout pointer was not folded onto the 24-bit bus — now masked, RED/GREEN);
  a misaligned `uint32_t*` store (now `wr32`); the saved-D5 offset pinned only against the header both shores read (now against
  the ROM trap entry's own frame); Tier 3 met by CASE CHOICE — a 3-byte AUX: Fwrite at 1.098 while the 1-byte form was 1.17 and an
  empty redirected Cconws 1.87 — fixed by one noinline call per arm with the resolution inlined (1-byte AUX: 1.08, Fseek on CON
  1.07, the six old dispatch rows back to 0.78-0.80), the SHORT rows registered, and the empty Cconws ACCEPTED at 1.71 on its
  measured mechanism; and an oracle-only record poke that was a comparison MASK disguised as input — now `case.run(dropped=…)`,
  a span dropped by name with its reason. Mutation 144/156 over the band (survivors equivalent / unreachable / unpinnable,
  listed in the rows). Remaining in GEMDOS: the E_CHG recovery behind the termination record's longjmp (see `## Not
  reconstructed`); the aes/desk boundary and VDI/Line-A are the next components.
* **Wave 10 (2026-09-26) — VDI + LINE-A FOUNDATION.** A read-only map of `$fc9f0c..$fd2f21` (199 functions; the Line-A
  rasterizers set up then `jmp` through RAM vectors `$2A24..$2A38`, which boot fills with the CPU set — ~11 KB of CPU pixel
  loops Ghidra never decompiled; the blitter set unreachable on this machine), then ONE foundation agent: `include/vdi/`
  headers (every field cited, width-tagged), `test/vdi.py` (records by name, the workstation staged AS THE DISPATCHER LEAVES
  IT — record + its 21 copies into Line-A, pinned against the ROM's dispatcher — byte-wise merged pokes, screen/pixel helpers
  and a compact screen diff, run doors for functions, register-contract primitives and the Line-A exception), shared machinery
  hoisted for every component (`case.merge_pokes` / `verified_row` / `Result` / `continued` / `SLACK_FILL`; the host-slot table
  moved to `include/host_slot.h` + `src/host_slot.c`; `include/ram_vector.h`), and tier3 deriving every VDI row from its
  `VDI_ROM_*`/`_OPCODE` pair (the kit's `os.h` already owns `VDI_<FN>` as opcode numbers, hence `VDI_ROM_`). Review (2 finders:
  every header field correct) found the staging helpers would have tested the WRONG MACHINE silently — the dispatcher's copies
  not staged, pokes replacing each other by address, non-fields accepted as fields, an unbounded ptsin — each fixed RED→GREEN.
  Worked examples: `vsf_perimeter` 0.72 and `$a000` 2.43 (accepted: (N), the dual of (M) — a C core answers in D0 alone, so
  several answer registers go through a results pointer; Tier 1 compares all of them, Tier 3 holds D0).
* **Wave 10 band 0 (2026-09-26) — the VDI's HELPERS, SETTERS, INQUIRIES, PALETTE and the PIXEL / SCANLINE primitives.** Four
  agents, 70 routines: `src/vdi/helpers.c` (the math/geometry/text helpers, `vr_trnfm`), `attributes.c` (every attribute setter,
  `st_fl_ptr`, `arb_corner`, the vex exchanges), `inquire.c` + `palette.c` (the inquiries, `vs_color`/`vq_color`), `raster.c` (concat,
  `$a001`..`$a005`, the three arms of `$a003` incl. the diagonal Bresenham that runs code BUILT ON THE STACK, and the CPU bodies of
  vectors 6/7/8). THE USER'S POLICY for the hand-written 68000 — C first, a byte-pinned `.S` where the C is over 1.10 — ran for the
  first time: 22 routines ship as `helpers.S` / `palette.S` / `raster.S`, every one BYTE-EXACT to the ROM (named encodings, no
  avoidable excusals; raster's cross-region displacements and its fringe-table reference pinned to their exact relocated values) and
  1.00 on every `.S` row. REVIEW (5 finders) found the policy had NO MECHANISM behind it — the bench linked both twins and ~40 over-bar
  C rows were justified by hand-typed prose — now ONE table, `include/vdi/transcribed.h` (`include/transcribed.h` since the AES
  foundation; entry, ROM routine, C core, the registers it leaves changed vs the GCC ABI), from which Tier 3's rule (T) is DERIVED (a transcribed routine's C rows pass only while every
  `.S` row is ≤ the bar — shown RED on a deleted and on a drifted `.S`), the future ROM build's contract (`atari/target.mk`
  TRANSCRIBED_*, pinned) and the `.S` entry declarations for C callers. Real divergences fixed RED→GREEN: the palette address not
  folded to 24 bits (30 low-res indexes wrap into the vector page), `vq_color`'s and the inquiries' read points, the four colour
  setters' bound wrapping at DEV_TAB[13]=$8000, concat's shift count (mod 64, ≥16 sign fill), get_pixel's word accumulator; and the
  tests made honest: a weakened mutant restored (row placement by BYTES_LIN), the "unreachable" PLANES>8 guards reached, the `.S`
  pattern paths exercised, ptsout store-order overlaps, the code-pointer masks narrowed to the registers that really hold code.
  Names unified: `VDI_ROM_*` / `LINEA_ROM_*` for routine addresses. FINDINGS: no setter updates the dispatcher's Line-A copies (Line-A
  draws with the old write mode/clip until the next VDI call); a pattern style carried into hatch points PATPTR at MAP_COL; vqin_mode
  does not round-trip; vqt_name writes 34 words and reports 33; smul_div's `neg.l` rounding; clc_dda's equal-size arm unreachable;
  concat's shift table starts at its own `rts`; `$a005` stores clipped corners on a miss. Mutation (logged, private builds): helpers.c
  83/88, attributes.c 105/108, inquire+palette 92/92, raster.c 89/91, raster.S 55/57, helpers.S 32/33 — every survivor named in the
  sweep logs and equivalent or a documented memory smash.
* **Wave 10 band 1 (2026-09-27) — BIT-BLIT, TEXT RASTER, POLYGONS & FILLS, MOUSE & INPUT.** Four agents, ~50 routines: `blit.c`/`.S`
  (the threaded CPU blit engine — 57 absolute fragment addresses relocated and pinned — `$a007`, `$a00e`, vro/vrt_cpyfm, vr_recfl),
  `text_raster.c`/`.S` (TextBlt $fd1df6, the ROM's largest hand loop, and fast text; the `.S` generated from the disassembly),
  `fill.c`/`.S` (`$a006`, clip_line/polyline/plygn, the contour seed fill with DRI's globals and a 1920-word queue), `mouse.c`/`.S`
  (sprites, hide/show, vsc_form, the mouse ISR, the VBL cursor, mouse_init/off, the polls, locator/choice/string). REVIEW (5
  finders) found ~12 real divergences — each RED-before/GREEN-after: the blit re-tests P_ADDR PER PLANE and re-reads MIDDLE_COUNT
  per row; an odd TextBlt op index is the ROM's address error and an op slot naming an effect fragment must halt (mode 44 + LIGHTEN
  hung the suite); `$a006` takes an overflowed crossing's sign from the 32-bit PRODUCT; the contour fill's walks are true signed
  compares; polyline clears LSTLIN and v_get_pixel answers BEFORE their reads; end_pts' `adda.w` sign extension and A5 drift;
  draw_sprite saves a row BEFORE reading its form words; the mouse ISR reads through the A0 a user vector hands back — and a
  BUILD-CONTRACT HOLE (GCC inlined transcribed C cores into their callers: now `TRANSCRIBED_CORE` = noipa on all 42). The 16
  hand-typed "(T) through a call" acceptances are GONE: a SECOND bench blob (`build/bench_shipped/`) links every C caller of a
  transcribed core to the `.S` through glue thunks GENERATED from the table (`bench/shipped_glue.py`) — band 0's deferred call-site
  glue, built and exercised by every bench run — and legend rule (T→) prices those rows AS THEY SHIP (0.78–1.08; drifting a callee's
  `.S` reddens them, shown). ONE register-carrying RAM-vector hook (D0/D1/A0) in staged_call.h; one Alcyon signature registry;
  cross-file `.S` relocations must land in a byte-pinned region; every ROM-address-as-data site enumerated (test_vdi_rom_data.py).
  MUTATION TOTALS WERE UNRELIABLE (every sweep counted any nonzero exit — timeouts and an agent's `pkill` SIGTERMs — as a kill):
  a STRICT classifier (README "Mutation sweeps") found 10 real holes, all now killed; honest totals blit.c 101/109, blit.S 54/56,
  text_raster.c 203/224 (six thicken-first survivors equivalent by argument, not proof), text_raster.S 24/28, fill.c 123/145 (11
  abnormal = non-terminating mutants), fill.S 47/51, mouse.c 157/161, mouse.S 58/59. FINDINGS: the ROM's CONTOUR FILL CAN HANG
  (only SEEDABORT stops it) and `v_choice` REQUEST MODE HANGS FOR EVER; `$a00e`'s bit 4 is the pattern flag; TextBlt modes past
  19 read an easter egg as op indexes; vdi_locator writes the caller's intin; plygn permanently increments the caller's contrl[1].
* **Wave 10 band 2 (2026-09-28) — WIDE LINES & MARKERS, the TEXT LAYER's C, the TIMER & SCREEN plumbing.** Three agents, 22
  routines: `lines.c` (v_pline, v_pmarker and the Alcyon geometry of a wide line — cir_dda, perp_off, do_circ, wline, arrow, do_arrow —
  all C, five host slots standing in for the frames the ROM points LINEA_PTSIN at), `text.c` (text_init, make_header, vst_height/point/
  font, vqt_extent/width, vst_load_fonts over REAL fonts: byte copies of the ROM headers, a GDOS set behind the ring, Intel-order forms,
  a proportional face with a HOR table), `screen.c`/`.S` (v_clrwk, setres, init/restore_timer_mouse, the etv_timer tick, and the BIOS
  span clear `$fc4b7c` moved out of `pexec_load.c` into a byte-exact `.S` because its C is 3.87× the ROM's `movem` loop — so the Pexec
  loader now prices THROUGH it and its rows fell: 0.84 → 0.79). `timer_tick` ALSO ships as the ROM's own 24 bytes, on the
  trap1.S/isr.S entry precedent rather than the >1.10 rule: etv_timer holds its address and the C core does not take that convention
  (transcribed.h row = the vector set, measured; USER_TIM stubs clobber everything so the `movem` bracket is pinned; `.S` 1.00, C 0.98).
  REVIEW (3 finders + a seams pass) found real defects, each fixed RED→GREEN: TARGET STRICT ALIASING merged vqt_width's HOR_TABLE
  re-read after a ptsout store (Tier 3's second differential, one byte at $c4049) — `-fno-strict-aliasing` now in `atari/target.mk`
  for every target build, PINNED by asking make for the expanded flags; it moved rows by hundredths (five pinned Bconout acceptances
  re-pinned, vs_clip respelt faithfully to one PTSIN read, 1.06 → 0.83); setres's switching arms were pinned ONLY AS HALTS (3 mutants
  survived) — now the mode is named in the halt and read off the ROM's pushed word, the image checked unchanged in a shared-memory
  child; do_arrow's hand "(D) through smul_div's glue" acceptance was the band-1 "(T) through a call" in disguise — replaced by a
  DERIVED rule (T→G `glue`): every (T→) row is profiled on the shipped blob, the cycles inside the sized glue thunks netted out, and a
  row over the bar passes only if its NET ratio is ≤ 1.10 (arrow 1.10/0.99, do_arrow 1.14/1.01 and 1.13/1.01, vqt_width 1.15/1.08; vq_key_s
  and vdi_choice stay accepted, OVER even net); the WORST realistic rows registered (width 1 for arrow/do_arrow, a bus high-byte chain
  for vst_height, ptsout over HOR_TABLE); the poison opt-outs narrowed to one named constant (`vdi.READS_A_POINTER_IT_WRITES`) used only
  where the pass reads the I/O page (arrow, the four text-size routines) — v_pmarker's pass now really attributes; helper duplication
  collapsed (one COLBIT loop, one contrl/workstation/device-table word helper set, one `bus_dereference` idiom with its base-0
  precondition, one trap #14 helper header for five sites, one `refusal_over`), the init IPL mask pinned on the shipped ELF, and the
  call graph taught to see a function address loaded as an immediate (GCC had hidden make_header's act_siz calls from the pricing).
  MUTATION (strict, private .so per mutant): lines.c 89/98 (6 equivalent, 3 abnormal = the host's named zero-divide refusals), text.c
  104/109 (5 equivalent), screen.c 36/45 (6 equivalent span splits, 3 abnormal = host aborts on a detection), the tick `.S` 8/8 by the
  byte pin. FINDINGS: the wide line leaves the CALLER's contrl[1] at 5 and v_pmarker at its last polyline's count, with LINEA_CLIP
  left 1; the quarter circle is cached by WIDTH only; nothing bounds cir_dda's width (79 writes STR_MODE); the dead arrow end-style bit
  also draws round discs; `$fd3664..$fd36eb` is the marker-shape data; vqt_extent at 270° answers the wrong box and sums in the shared
  word at `$1706`; vst_height/vst_point after vst_unload_fonts take ADDRESS 0 as the font; text_init turns Intel forms WITHOUT flagging
  them (every v_opnwk re-swaps); vst_load_fonts makes no GEMDOS call; on a colour ST every setres word but 1 and 3 opens LOW; a
  second v_opnwk CHAINS THE TIMER TICK TO ITSELF (unbounded recursion on the next tick); restore with a negative NEXT_TIM leaves the
  VDI's tick installed.
  THE CODE-REVIEW GATE (my-code-review, high) then fixed, RED→GREEN each: `span_bytes`' host bound spelt as a sum wrapped for a `to`
  below `from` and let the host clear run off the image (SIGSEGV) — now `width <= RAM && driven <= RAM - width`, pinned by a child-process
  abort; the `xbios.h` trap helpers took plain `d` inputs, so a second argument took callee-saved D3 and every caller saved it (Tsettime
  0.76 → 0.93, Tsetdate 0.60 → 0.66, mouse_off +16) — inputs now bound in D0/D1/D2 as `+d`, HEAD's cycles back and setres 0.02 better;
  vs_clip's single PTSIN read is now pinned by a ptsin laid over Line-A's own INTIN/PTSIN pointers (the per-word form reddens); the init
  mask test now orders the NEXT_TIM store before the SR restore; the call graph's immediate rule reads only a `move.l`/`movea.l` of the
  constant into a register or frame slot (a compared or stored constant equal to a function start no longer forges an edge; both
  graphs unchanged). Harness: one `symbol_table(elf)` and one `vdi.SHIPPED_ELF`; the glue read as slices (`emu.prof_slice`, ~27 ms a
  (T→) row, was ~49); `glue_cycles_of` defaults 0; `refusal_over` encodes its I/O seed through the kit. Cleanups left every object
  byte-identical but one operand swap (`asks_for_arrows`).
* **Wave 10 band 3 (2026-09-28) — ARCS & ROUNDED BOXES, GRAPHIC TEXT, the WORKSTATIONS.** Three agents, 12 routines, all Alcyon C:
  `arcs.c` (clc_pts, clc_arc, gdp_arc, gdp_ell, gdp_rbox, entered by `jsr` as vdi_gdp's arms leave the machine; the seven arc-scratch
  words named, two of them below CUR_FONT; v_pline and the rounded box share `line_style_mask`/`set_line_attributes` with no non-arc
  row moved), `gtext.c` (v_gtext and d_justified over REAL fonts — the ROM faces and GDOS-shaped RAM copies — through TextBlt, the fast
  path and `$a003`; `style_asks_for`/`font_flag` hoisted with objects byte-identical; the empty string was 1.71 until the body moved out
  of line behind the count test), `workstation.c` (init_wk, v_opnwk over a FILLed machine with the shifter and palette declared and
  its switching arms pinned as halts equal to the ROM's image, v_opnvwk/v_clsvwk/v_clswk through the REAL `trap #1` into the ROM's
  GEMDOS, their list built by chained opens and closes that reach the duplicate-handle bug by themselves). Every row is priced: (T→)
  through the shipped blob at 0.42–1.07, six (T→G) at 1.10–1.17 shipped and 0.90–1.02 net, init_wk plain at 1.07; no acceptance.
  REVIEW (3 finders + a seams pass) found real defects, each fixed RED→GREEN: v_gtext RE-READ CUR_FONT for the first glyph where the
  ROM draws glyph 0 in the A5 font it loaded at entry (`$fcd76e`, reloading only after each TextBlt at `$fcdc38`; a font at `$b0010`
  pins it, and the "DELY stored once" mutant it kills had been labelled equivalent); place_origin read the font's lines before the
  DESTX store. TESTS WEAKER THAN CLAIMED: v_clsvwk's walk never crossed more than one link (`while` → `if` survived; now close the last
  of four and the second of two 3s — first match wins, the first 3 falls off the list still allocated); arms called unreachable were
  reached (H_ALIGN > 2 / V_ALIGN > 5 through the workstation record's copies, the 3600-rotation underline via vst_rotation(3150),
  vsl_width's stored negatives −3 / −1, seven WRAPPED rounded boxes that do return — the "y wraps" one killed a half-height word-wrap
  hole); cases that had silently taken the fast path (x on a byte) made TextBlt twins; the WORST realistic rows were unregistered
  (d_justified's long spaced lines scrolled away, 1.11 / 1.11 / 1.13, and v_gtext's ninety missing characters, 1.06) — registered;
  a Malloc spy (= 308) killed the Malloc(307) survivor. Band 1's HOST TextBlt OVERRAN its scratch: a huge WEIGHT or a wide glyph turned
  SIGSEGV'd/SIGBUS'd in the pre-pass and the quarter/half turns, and the DDA SCALE copy of a 22,330-wide glyph doubled wrote 37,954 B
  over the vectors, VDI and Line-A RAM before anything refused — both now named host refusals (`require_scratch_room`, a row at a time
  `require_scaled_row_room`; legitimate copies peak at 228 B, more than one 204-byte half, inside the 532 B before the PTSIN copy),
  target `.text` identical. The GEMDOS-trap rows were first UNPRICED ("the whole-image relation differs by nature"); now priced over the
  STAGED recording `trap #1`, and the kit's `RomBench.measure(dropped=)` names `[$2848, $284c)` LINEA_RETSAV. THE CODE-REVIEW GATE
  (my-code-review, high) then made that drop rule PER BYTE and SHARED: `rom_bench.vet_dropped` refuses a dropped byte the ORIGINAL did
  not write (a drop one longword wider than the park went through before) or a truncated ledger, and `case.run` calls the same rule —
  which TIGHTENED committed Tier 1 drops: the GEMDOS door's 0x100-deep stack drop covered 124–200 bytes the ROM never writes, and the
  save-area/termination-record drops were dead in the no-trap cases and two never-nesting Cconrs cases; they became
  `case.run(dropped_windows=)` (only the window's bytes the original stores are dropped, the rest compared again). A Tier 3 drop now
  needs `undropped=` (a companion differential over the row's own pokes that drops nothing, run by `test_tier3`). The staged trap's
  ledger APPENDS (8 entries; a v_clswk mutant freeing records in a swapped order survived the single slot, now red; +4 insns / +48
  cycles a trap on BOTH columns, so seven rows moved toward 1). The call graph QUALIFIES a function name objdump gives twice by its
  defining FILE (`readelf` FILE symbols; two statics' `.isra`/`.constprop` clones had folded into one node), an address-less
  reference to a shared name reaches every node of it, and a qualified base that is a row symbol or a transcribed core is refused.
  `declare_alcyon(host_arguments=)` lets glue be generated for C calling gemdos_call (its thunk now executes, 136 cycles). DRY: one
  `table_entry`/`word_entry`, `copy_words`, `set_work_word`/`set_work_long`, the colour clamp/map helpers and clamp constants in
  `attributes.h` (init_wk's high-first interior and fill-style clamps kept spelt out: 2–4 cycles through the helper), one XFM family,
  `VDI_POINT_WORDS`; the ROM-data census now reads `include/vdi/*.h` inlines. MUTATION (strict, private .so per mutant): arcs.c 82/83
  (1 equivalent), gtext.c 143/144 (1 abnormal = the named scratch refusal), workstation.c 141/152 (8 equivalent, 3 abnormal = a host
  abort and two non-terminating walks), the gate's C changes 15/15. FINDINGS: v_opnvwk hands out a DUPLICATE HANDLE after a close from
  the middle (1,2,4 → 3 appended, then a second 3 inserted); init_wk stores the fill style 1-BASED where vsf_style stores it 0-based,
  and line type 0 as −1; v_clswk leaves the physical WS_NEXT naming freed memory; v_clsvwk's walk has NO END TEST (a record not on the
  list wanders through address 0's vectors); gdp_rbox sorts through its CALLER's A5 (= PTSIN at both of vdi_gdp's `jsr`s); an OUTLINED
  box whose wrapped segments send clip_line into a cycle never returns; the last arc point is END_ANG, never START + DEL, and angles
  are never normalised; the HOR table is read ONE BYTE a glyph where vqt_width reads (left, right) pairs; centred or right-aligned
  text leaves VDI_RESULT = 1 and the extent in `$1706`/`$1708`; a non-right-angle rotation draws at the stale DESTX/DESTY; the map's
  "`$fd2e84`" is vq_color, v_gtext is 1862 bytes (cfg.txt said 1682), and `$fcd9f2`'s `ijmp` is the V_ALIGN switch (`$fd3990`).
* **Wave 10 band 4 (2026-09-29) — the GDP, the ENTRIES, the ESCAPE: the VDI complete (but the blitter).** Three agents, five
  routines and Scrdmp's export: `gdp.c` (vdi_gdp `$fcbbcc`, the ten-arm switch at `$fd3954`, inline Alcyon C — the bar, circle and
  ellipse arms do their own set-up, every other arm `jsr`s a band-3 worker), `entry.c` + `entry.S` (linea_dispatch `$fc9f0c`,
  linea_init's `.S`, vdi_entry `$fc9f9e`, vdi_dispatch `$fca9f6`), `escape.c` + `escape.S` (the escape `$fc427a`, 22 arms), and
  `vbl.c`'s static `screen_dump` exported as `xbios_scrdmp` ($fc0d50). vdi_gdp's arms PROVE BAND 3'S STAGING BYTE FOR BYTE: the real
  arm runs over the staging band 3 used for each worker and its final machine is held to the worker's run from it
  (`vdi_gdp.assert_same_machine`), so band 3's "machine as the arm leaves it" is measured rather than trusted; the aspect and
  ellipse-reading helpers moved into `vdi/arcs.h` inlines with every arcs row unmoved to the cycle. THE ENTRIES: the Line-A exception,
  `$a000` and the `trap #2` entry ship as ONE byte-pinned region `$fc9f0c..$fc9ffb` with 16 declared words (`$a000`'s two `lea`s and
  the 14 table longwords of `.S`-shipped primitives relocated to their entries; `$a009`/`$a00f` keep the ROM's) — the timer_tick
  precedent, entries with a register convention no C function has; the dispatcher ships as C through a new `staged_call.h` shape,
  `call_vector_keeping`, which saves the callee-saved file round the `jsr` only (the ordinary shape measured 1.09 on a lookup that
  calls nothing). THE ESCAPE, under the user's hand-68000 policy: its word table points mostly INTO the VT52 driver's own ESC bodies at
  the addresses ESC's tables name, and the author's first cut (C entering nine per-body `vt52.c` exports, 32 hand acceptances up to
  3.13) was refused at the fix list — the escape is hand 68000 over the bar, so its OWN code ships as a byte-exact `.S` (four spans,
  386 ROM bytes, 27 exact relocations incl. a new table-based `Relocated.base` and `Relocated.thunk`) with 13 `.S`→C thunks into the
  console bodies, which stay C under Bconout's acceptances; ESC E's thunk sits at the ROM's own body address, so v_exit_cur's fall
  through and v_enter_cur's `bsr.s` keep the ROM's bytes. THE DERIVED (T←) `own` RULE, from the code-review gate, replaced a LOOSE
  (T) extension (a written entry for a `.S` row carried its C rows) and the 24 hand `vdi_rom_escape` acceptances that leaned on it:
  every `.S` row of a routine that calls C is PROFILED on both sides — on ours the cycles inside its sized thunks and the C they reach
  (the m68k call graph's closure) are subtracted, on the ROM's the ROM-window cycles inside its transcribed spans are its own; the row
  is `own` iff its own instructions are within the bar AND every cited Bconout(CON:) acceptance still stands, an own ratio over the bar
  reds a row even when the row is under it, and a written entry for a `.S` row now carries NOTHING. For that the KIT PROFILER COUNTS
  THE ROM WINDOW (`shim.c` tallied PCs below 1 MiB and only in `run_bench`: now `PROF_ROM_SIZE` slots after the RAM ones, one
  `osh_prof_slot`, `prof_tally()` in both loops, `emu.prof_cycles(lo, hi)`; the RAM slot layout unchanged). RED first: a +24-cycle
  spill in the escape's dispatch reds 26 of 38 rows; deleting each cited acceptance in turn reds the rows it carries. THE REVIEW AND
  THE GATE found real defects, each RED→GREEN: (1) THE BIOS CONSOLE'S 24-BIT WRAP, a LATENT Bconout DIVERGENCE — a cell address past
  16 MB (vs_curaddress row 0, or an ESC Y row byte below the $20 bias through v_curtext OR Bconout) is where the ROM wraps to the row
  above the screen and the host aborted; the gate made it ONE console bus policy, `vt52.h`'s `console_screen_block` (form, wrap, then
  bound) for every console screen writer — cursor, glyph, clear, both scrolls (`test_bios_console_bus.py`, 7 cases, and a Bconout ESC
  Y case that also newly DRIVES `bpl` against `bcc` on the row clamp); target objects byte-identical. (2) The Line-A dispatch's
  declared clobbers missed A6 (`$a007` adds 76, `$a00d` loads it) — the case choice hid it; a `$a007` transcription row measures it.
  (3) FIVE dispatcher mutants survived the battery, two called equivalent wrongly (the handle read after VDI_RESULT's clear with
  contrl[6] on it; MONO_STATUS from a record partly over `$2610`) and three never swept — each killed by a new differential. (4) The
  ptsin copy's DIRECTION and the dispatcher copies' ORDER against the ROM were unpinned (a backwards copy and 4 of 20 adjacent swaps
  fully green) — now one ordered `vdi.DISPATCH_STEPS` list the ROM's stores are held to (20/20 swaps and 24/24 dropped steps red).
  (5) Scrdmp's COUNT and ORDER: `scr_dump` called twice, or the flag set before the call, passed all 282 escape + VBL tests — a
  recording stub now. (6) THE LAYER-WIDE BUS POLICY for the VDI accessors: a trap #2 block with top-byte-dirty pointers SIGBUS'd
  vsm_height/vqin_mode and read outside the image in v_pline/wline — `vdi.h`'s call and workstation accessors now SUM THEN MASK (the
  68000's `d16(An)`), `caller_word` serves a held cursor and vdi_wline's PTSIN reads (`test_vdi_bus_pointers.py`, 7); target objects
  identical but one GCC-internal `CSWTCH` label. Also: the WORST realistic rows registered (the width-3 outlined box, the TALL ellipse
  — band 3's gdp_ell row too, 1.01 → 1.02 — v_curtext's one ESC / one NUL, escape 20); the two light mouse paths the escape's `jmp`s
  leave to the ROM priced on v_show_c/v_hide_c themselves; each escape arm's transcription mask derived per ARM from what the two
  measurably disagree in; the perimeter constant's four spellings → `vdi.h`'s one; `next_of`/`handle_of` hoisted into
  `vdi/workstation.h`; `M68K_Dn`/`M68K_An` for entry.S, fill.S and blit.S; `c_call_glue.h` shared by isr.S and escape.S;
  `vdi.CallerPool.staged` with a pool-overlap refusal; `assert_same_machine`'s 16 MB Python walk → `harness.differing_addresses` and
  the order search once per placement (≈4 min → 48 s). THE MUTATION TOOL: `privlib` swapped only `src/` files, so a HEADER mutant
  was compiled UNMUTATED and counted SURVIVED — earlier bands' header totals could only UNDERSTATE kills, never claim a false one; a
  per-tag shadow include dir fixes it, and a replacement nothing compiles is refused. MUTATION (strict, a private .so or blob per
  mutant): gdp.c 50/56 (5 equivalent, 1 unpinned) + the perimeter constants 6/6; entry.c 103/112 (5 equivalent, 2 unpinned
  host-only, 2 abnormal); the escape's C 68/71 (1 equivalent, 2 abnormal — the named zero-divide refusal and the bus-wrap revert, each
  caught by an abort) and its `.S` 8/9 (1 equivalent) — 235 of 254 killed, 12 equivalent, 3 unpinned, 4 abnormal. ROM FINDINGS:
  vdi_gdp is 434 bytes (cfg.txt said 92), `$fcbd5e`'s `bra` and `$fcbd60`'s `bhi` are dead and D7 is "restored" by `tst.l (sp)+`; the
  bar's outline is the FILL colour through polyline (line style, colour and width ignored), and only for WS_FILL_PER exactly 1;
  v_opnvwk inserts its duplicate handle AHEAD of the older one, so the newest wins and the older cannot be reached by handle until it
  closes; the entry doubles the point count in a WORD ($8000 copies nothing, $8200 copies 1024 words with no cap) and gives the count
  back through a re-read LINEA_CONTRL, which a function's intout can move; opcodes outside both tables still load the workstation;
  v_opnwk and v_opnvwk ignore contrl[6]; vdi_entry is 94 bytes (the map: 92); the escape serves 101 (v_offset) and 102 (v_fontinit)
  beyond the documented 1..19, its bound is UNSIGNED, vs_curaddress validates nothing (0 → $ffff, which with the cursor drawn inverts
  a cell far outside RAM), v_dspcur writes the caller's intin[0] and ignores ptsin, v_curtext's count is an unsigned `dbf` (≥ $8000
  walks up to 128 KB), v_offset never re-places the cursor, v_fontinit has no zero-divisor guard, vq_chcells stores columns first and
  the table's entry 0 is its `rts`; the map's "`$fcb148` (hide cursor)" is v_hide_c, the MOUSE hide; and `$fc4a42` is escape 102,
  whose body past its intin read (`$fc4a48`) is what the console re-init `$fca914` `bsr`s into.
* **Wave 11 (2026-09-30) — AES FOUNDATION.** THE MAP, read-only over `$fd9eca..$fefff3` (736 functions, `projects/tos102us/AES_MAP.md`
  + `aes_map/`): the aes/desk boundary is `$fe387c` — the desk (`$fdb014..$fe387b`) is a SUBROUTINE of the shell in PD0
  (deskmain `$fe272e`, called once from sh_main) and calls the AES's INTERNAL routines directly through Line-F, never
  `trap #2` (its own binding layer `$fdde54..$fde4cc`, each `dsptch(); <internal>()`), so the AES's testable surface is ~60
  internal entry points and the desk can only follow them; the boot snapshot sits INSIDE the dispatcher's idle loop (`rlr`
  NULL, `indisp` 1, both PDs on `nrl` in evnt_multi, the CPU in `idle` polling the keyboard through the VDI); every
  internal call is a Line-F word through a Malloc'd RAM copy of the handler (`$2c` → `$cc0e`) that SELF-PATCHES its own
  `movem` mask word at `$cc44` on every masked Alcyon return — a word a C candidate never writes; and `decomp.c` is
  UNRELIABLE in this range (472 of 726 functions end in `halt_baddata` at a Line-F return, ~355 Line-F calls mis-decoded as
  coprocessor ops, some calls simply absent, every call's D0 invisible) — port from the map's own Line-F-aware disassembler.
  The map was wrong in places a body read corrected: "optimize" is not all hand 68000 (`$fecfb2`, `$fed19e`, `$fed27c`,
  `$fed382` are Alcyon C), three names in it were misassigned (`$fed19e` is ob_sst, everyobj is `$fed27c`, get_par
  `$fed382`), `$b74a` is window 0's ORECT list and not a tree, the three UDAs are NOT one stride, and the Line-F table names
  42 routines more than once. THE DOOR: `test/aes.py` (fields through `test/layouts.py`, the width-tag reader hoisted out of
  vdi.py; the ROM-routine naming rule hoisted into `test/routines.py`, by which tier3 labels every VDI/Line-A/AES row; every
  component's rows and drops through `case.Rows`; `staging.Registry.require_claimed`; `table_entry` moved to
  `m68k_idioms.h` with every other source's m68k code byte-identical), the addrs.h AES block (86 routines, 62 `_OPCODE` pairs
  held to the dispatcher's arms, the 48 table gaps to its default arm), `include/aes/{aes,objects}.h` (25 table immediates
  pinned against the ROM, the tables tiling THEGLO). THE `$cc44` DROP: the mask word is dropped by name
  (`aes.LINE_F_MASK_WINDOW`, a window: only where the ROM's run stores it) and every priced row drops it at Tier 3 with its
  UNDROPPED companion, the word staged at the value the run leaves. AES CASES RUN POISONED: the foundation found the kit's
  attribution pass could not coexist with a drop (it pre-inverted every oracle-written byte before `case.run` could drop
  one, so a case whose ROM run rewrote the word failed the pass and one that changed it skipped the pass in silence) — the
  kit now takes the drops as DATA, `differential(dropped=drops.Dropped(spans, windows))`, leaves them out of the plain
  compare BEFORE the pass's gate and neither poisons nor compares them (the gate then held fixed spans to the PLAIN run
  only, the re-run cutting only windows, and `_vet_poison_is_attributable` leaving dropped bytes out of its clash set, each
  RED first; `tools/recreate_kit/drops.py`, which imports nothing, so Tier 1 no longer imports the Tier 3 module).
  COMPONENT-NEUTRAL `.S` MACHINERY: the byte-exact transcription table is `include/transcribed.h` (was
  `include/vdi/transcribed.h`), its machinery `test/transcription.py` (moved out of vdi.py, ~560 lines), its test
  `test/test_transcribed.py` (was `test_vdi_transcribed.py`), `atari/target.mk` compiling `src/vdi/*.S` and `src/aes/*.S`;
  an AES `.S` is held to its EXECUTED path (the oracle's cycle-per-PC profile over the row's cases) running no Line-F word
  and reaching no return tail outside its own pinned region — a static word scan was tried and REFUTED (`cmp.w #-1` at
  `$fed04a` reads as a Line-F return word); a scratch `src/aes/rect.S` for `$fecd22..$fed070` went through the whole
  machinery at 1.00 and was not committed; every object, both blobs and every tier3 number byte-identical across the move.
  THE KIT WATCHDOG: a mutant that makes host C spin used to hang the run; a per-call faulthandler guard inside
  `harness.differential` was built, then REFUTED at the gate four ways (the dump lost under fd capture, every differential
  erroring under `--capture=sys`, pytest's own `faulthandler_timeout` silently disarmed, only two of ~300 call paths
  covered) and replaced by a PLUGIN, `-p recreate_kit.watchdog` (kit.mk's `test`/`guarded`, the kit's Makefile): one timer
  per TEST, written to a dup of the REAL stderr taken at configure, budget `TEST_BUDGET_SECONDS` = 300 s from the measured
  maxima (buggyboy's `test_hi_fuzz` 46 s is the longest; tos102us 5.8 s), `--watchdog-seconds` to change it, an outer
  `faulthandler_timeout` REFUSED rather than clobbered. THE MUTATION RULE it forced: a watchdog exit or a segfaulted worker
  is under xdist a "crashed" test counted in `N failed` with exit 1 — the shape of a kill with no assertion — so a run is
  KILLED only when it failed MORE tests than crashed (README "Mutation sweeps"); re-classifying the saved tails moved TWO
  verdicts KILLED → ABNORMAL, so the foundation's recorded kill tally was 2 too high. REVIEW (2 reviewers) AND GATE (5
  finders) FINDINGS, each fixed RED→GREEN or pinned: the kit gap above; test_status's table pattern stopped at `$fd` and
  would have left every AES row unpinned in both directions (widened to `$fe`); the pointer arguments' 24-bit bus (a
  top-byte `BUS_TAG` on every pointer); ob_offset's two call words ($f208 ×4, $f154 ×3) pinned site by site; the sixteen
  fork-function immediates enumerated (`aes.FORK_FUNCTION_IMMEDIATES`: six queue pushes, three ap_tplay stores, three
  compares in forker's recorder, four in ap_trecd — the review had counted six), with `AES_ROM_{T,K,B,M}CHANGE` in addrs.h;
  rc_intersect at the bus top (below); the Line-A `.S` rows now labelled by the one naming rule (`Line-A linea_hline
  (.S)`). MUTATION (strict, a private .so per mutant): 35 — 30 killed, 3 equivalent (ob_offset's swapped clears,
  rc_intersect's origin ties and extent-before-origin), 2 ABNORMAL (`object_field` and rc_intersect's clip without the bus
  mask: only a segfaulted worker); get_par 5/5 (its three spins killed by failed assertions beside the crashed tests),
  ob_offset 7/8 + its answer word's bus mask, rc_intersect 12/14, the headers 5/5 (OB_X, OB_TAIL, GRECT_H, the signed
  object index, the signed `table_entry` index); the kit's own — the four drop mutants, the watchdog's missing `file=`, its
  missing refusal and its missing cancel — all killed. The Line-F CALL path costs +15 instructions / +190 cycles through
  the staged caller; priced rows enter by `jsr`, so the ROM column carries the Line-F RETURN's cost and not the CALL's —
  conservative.
* **Wave 11 bands 0+1 (2026-09-30) — the AES's LEAVES and OBJECT/RESOURCE layer.** Five slice agents (0A the optimize
  layer's memory and string helpers; 0B the rectangle helpers, object text and state, ob_sst/everyobj and the DESKTOP.INF
  scanners; 0C gemrlist; 1A the object-tree operations; 1B the resource layer and the shell/scrap buffers), four reviewers,
  two fix agents (P the C and its harness, Q the kit and the shared Python) and a gate-fix pass: 90 routines, all ✅ but
  `dos_free` (a host argument), 290 AES Tier 3 rows. THE OPTIMIZE LAYER IS ONE BYTE-EXACT `.S`: 35 of its helpers measured
  over the bar in C (1.11–2.78 — two-to-three-instruction loops a compiler cannot match), and because the ROM's shared
  return tails `$fed066`/`$fed06a`/`$fed06e` are reached from strlen, streq, rc_equal and inf_what alike they share one
  region with every user, so 0A's `strings.S` and 0B's `rect.S` merged into `src/aes/optimize.S` — the object-text helpers
  laid out in it as unentered words; inside and rc_intersect ship as C (under the bar); merge_str's two `jsr`s relocated into
  the lmul/ldiv region; the executed-path check now names all three tails (the review found the third, `$fed06e`, missing).
  THREE DIVERGENCES FOUND BY REVIEW, each fixed RED→GREEN: ob_find STARTED AT -1 — the ROM steps back only when `dosibs &&
  lastfound != -1` (`$fea182`) and the C had dropped the second test as "redundant", and its model agreed by construction;
  everyobj CLIMBING ABOVE ITS FIRST LEVEL (a tree whose object names its sibling as ob_tail) — the ROM reads its own frame,
  the C read `across[-1]` with no refusal; and THE TOP-OF-BUS WRITES — a tree-table entry at `$00ffffff` sent rs_saddr's
  store 3 bytes past the 16 MB host image, and the same raw `image + address` sat in rs_gaddr, fix_long and the object
  accessors. The fix for the last is the SHARED BUS ACCESSOR FAMILY: `bus_span` and its byte/word/long readers and setters
  in `m68k_idioms.h`, ~12 re-spellings under 9 names in 8 files collapsed into it (three `word_at`s with three return
  types among them), the bound written so it cannot wrap (`at <= OS_BUS_ADDR_MASK - (bytes - 1)`), plus ONE GEMDOS trap
  helper (`gemdos/gemdos.h`'s `gemdos_trap_word_long`, the VDI's and the AES's copies deleted, one `HOST_SLOT_GEMDOS_WORDS`).
  THE KIT PRICES A >6-ARGUMENT CORE: its argument area holds six C arguments, and ob_sst (9), everyobj (8) and inf_fldset
  (7) were unpriced; `rom_bench._call` now enters OUR side with its stack pointer lowered by exactly the bytes that do not
  fit (the ORIGINAL reads the frame its case poked, unchanged) — 8 of the project's 1,111 Tier 3 calls, every other entered
  where it was — and `call_alcyon_object`'s 10-byte frame is really exercised (swapping its x/y pushes reds both everyobj
  rows). THE REAL-DATA RELOCATION CHECK IS EXACT: a fresh ROM copy of each resource, staged where start-up put it and
  relocated again, equals the snapshot byte for byte but for 17 named bytes the AES and the desk edited since — asserted
  `==`, where it had been a subset test over whole fields excusing 34. POISON OPT-OUTS ARE PER CASE, each measured by
  forcing the pass on: the edit battery runs poisoned with only its link longwords unpoisoned, gemrlist's ten green
  functions opted back in, rom_ram's four sites; the staged-trap battery stays opted out as a whole (below). THE GATE'S
  TWO FINDINGS: (G1) the recording `trap #1` handler's host twin stored through the ledger pointer it read out of the
  image, unbounded — the attribution pass inverts that pointer, so a poisoned run wrote into host memory (two false greens
  under xdist); it is bounded to the ledger now and refuses by name, and `AddressHook` records an effect that raises and
  fails the case (a ctypes callback cannot raise into C: it was printed and the run carried on); (G2) everyobj ON TARGET
  wrote `across[8]`/`down[8]` past its arrays for a valid 8-deep tree while the host refused — both builds now take the
  same named halt (`trap #7` on target, pinned by running the blob), tested only where the level moves (everyobj's rows
  unchanged at 0.71/0.69; a per-object test had cost 0.71→0.81). ROM FINDINGS (each pinned by a case): TOS 1.02's everyobj
  keeps its levels in two 8-word frame arrays, so an 8-level walk stores x over its saved A6 and y over x[0] (≥10, its
  return address) — REACHABLE, since objc_draw hands the caller's depth straight on and GEM programs pass 8; the ORECT
  pool's exhaustion is never checked (mkpiece builds its piece at `$0`, brkrct answers "no overlap" after cutting) and
  or_start leaves the desktop's ORECT on both the free list and window 0's list; ob_order of an only child to -1 rewrites
  the word 24 bytes below the tree; lbcopy's backward loop from 32,770 bytes up moves ONE byte; mul_div's overflow arm is
  ORACLE-DEFINED — DIVS's N is undefined there, Musashi answers -15808 for mul_div(1000,1000,1) and the machine (Hatari)
  -15809, so the C follows the oracle, the shipped `.S` is the machine's and no row prices it; wfill's guard tests the
  value, not the count; lstcpy counts in a byte (255 → -1); inf_gindex's count 0 walks 65,536 objects and inf_what never
  reads `cancel`; ob_center tests OUTLINED, not SHADOWED; fix_chpos's offsets run -127..128; get_addr's tree ≥ `$2000`
  reads below its table; rom_rsc_init neither checks its Malloc nor sizes the AES part right (5 bytes of the desk's);
  dos_alloc never clears DOS_ERR; the capture's `$9c40` is 2, a value rom_ram never tests. MAP ERRATA, fixed in
  `AES_MAP.md` and `COMPONENTS.md`: the TEDINFO text helpers reversed, `$fee4de` the bundle copy, `$fe3db4`/`$fe3e08` Alcyon's
  lmul/ldiv, `$fecc6c` strlen, the resources' real starts. MUTATION (strict, a private `.so` per mutant): the slices
  68/68, 97/104, 55/56, 73/74, 159/164; P's re-sweep of all five lists re-spelt over the new accessors plus 24 new, **490 —
  474 killed, 12 survived, 4 ABNORMAL** — the 11 survivors the slices argued equivalent and `bus_span`'s bound one long
  (equivalent: with odd addresses refused first every even address meets both bounds alike), the four ABNORMAL a named
  halt reached before the assertion; Q's kit mutants 3/3 (sp not lowered, off by 2, staged at STACK_TOP); the gate pass's
  everyobj halts 6/6 and G1's two RED-proved (the unbounded store crashed the worker; the swallowed exception passed).
* **Wave 11 band 2 wave 1 (2026-10-01) — the `trap #2` BRIDGE, SHELL FIND + RESOURCE LOAD, NEWRECT and the AES census.**
  Three slice agents (F the foundation, S the shell and resource load, N newrect and the census), four reviewers (R1 F's C,
  asm, bridge and door; R2 the measurement and census machinery; R3 slice S; R4 slice N and the cross-cutting conventions),
  two fix agents (X gsx and Tier 3, Y the shell, resource and newrect plus the conventions): 27 ✅ routines, `dos_sdta` and
  `dos_close` verified and unpriced (a host argument, dos_free's precedent). THE FOUNDATION: the AES's one `trap #2` is
  gsx2's (`$fecb6a`), over the parameter block at `$9466` — the "two direct trap sites" of the map are Line-F calls of gsx2.
  `include/aes/gsx.h`'s `gsx_trap` checks both hops on the host (vector `$88`, SYSVAR_VDI_ENTRY `$8c2a` → `$fc4ebc`), halting by
  name on either, then runs the VDI's C twin of its entry with the VDI's C cores bound per case; the target makes the real trap.
  gemgsxif's atoms verified end to end against the whole image, screen included (21 VDI opcodes reached); the Line-F-free five
  (gsx2, gsx_ncode, gsx_1code, gsx_mon, gsx_fix) ship as `src/aes/gsx.S` (four pinned regions, two relocations). Tier 3 gained
  mechanism (V) "through the OS": a row whose C reaches `trap #2` is priced on its OWN cycles (blob − glue against the AES
  text + Line-F handler, the trap path and the VDI in neither), derived and RED-proved (a 1,734-cycle delay: whole 1.06, own
  4.26 → OVER); the measurement itself refuses an OS remainder that differs by a cycle, and a row under the bar only net of
  its thunks reads `glue` as (T→G) (vst_height's large font 1.17, gsx_moff's v_hide_c 1.12 with them). gsx_moff's open nest
  is ACCEPTED at 1.23 (62 → 76: the image pointer and `$c86a`'s address, the C's floor, once its hide path was split off; it
  had been 1.52). SHELL FIND + RESOURCE LOAD over REAL GEMDOS on the staged RAM disk (the ROM's own AES and desk resources as
  files) plus a SCRIPTED trap — its own 68000 stub, whose ledger records every frame whole (10 bytes) — for the error arms and
  every Tier 3 row; sh_find's caller routine by a new `call_alcyon_pointer` (one pushed long; its target asm runs in the
  logger row). The two frames whose address escapes (sh_envrn's, sh_find's) are kept whole in host slots in the ROM's layout,
  plus the caller's saved A6's top byte past them. NEWRECT (`src/aes/wrect.c`, with w_getsize and w_getxptr) closes band
  0C's deferral. THE CENSUS: `test/rom_data.py` holds the scanner the VDI's census and the AES's share (the VDI's table and
  output unchanged), and `test/test_aes_rom_data.py` holds the AES both ways — its sources' ROM values by kind, and the ROM
  text's 39 immediates naming AES code (owner + band, the 16 fork functions folded in, `owed_by` once ported) plus its 10
  pc-relative data references — each direction proved by a planted use. The header's window GRECTs were mislabeled (+16 is
  FULL, +24 WORK, +32 PREV; TOS 1.02's WS_* are FULL 0, CURR 1, PREV 2, WORK 3, TRUE 4) — renamed. THE REVIEW (4 finders):
  R1 measured gsx_moff's acceptance above the C's floor (1.52 → 1.23) and six unpinned arms of gsx's wrappers (PTSIN put
  back on the hide path and by vsl_width, vst_height's chain past its first link, gsx_fix's reads after its stores and its
  32-bit address test, vr_recfl's tagged pointer) — the poison pass is VACUOUS on gsx_moff/gsx_mon's call arms (it inverts
  gl_moff and steers the ROM to the counter path), so staging pins them; R2 found (V) `net` silently stacking the (T→G)
  thunk lenience (now the `glue` rule) and the remainder check living only in a test; R3 found both frame-overrun HALTS one
  byte early (the ROM serves the input), sh_path's D6 argued for the wrong reason, top-byte cases missing for most pointer
  arguments and the ledger missing Fread's buffer low word; R4 found newrect's area test after the border wrap unpinned and
  the Tier 3 rows short of the worst realistic one. THE FIXES: X split gsx_moff, added the six RED-proved cases, the (V)
  `glue` rule, the in-measurement remainder check; Y moved the shell halts one byte later (a 0 on the saved A6's top byte is
  served as the ROM serves it; a nonzero byte or anything further halts; ROM-alone cases pin both sides), entered sh_path's
  cases with the dispatcher's D6 = 1, registered the worst rows (the failed loads 0.89/0.85, dos_sfirst found 1.05, sh_find
  with its routine 0.91, newrect over a desktop already in four 0.89), added top-byte cases for every reachable pointer and
  newrect's `$fffe` wrap case. MUTATION (strict, a private `.so` per mutant): gsx.c and the bridge 78 — 74 killed, 3
  survived (R1's equivalents), 1 ABNORMAL (the bridge handed pb+4: the host aborts); the (V) mechanism 9/9 and the `glue`
  rule 5/5; shell, glue, resource and wrect 67 — 66 killed, 1 survived (equivalent: DOS_ERR is already 1); wrect's first
  sweep 30 — 27 killed, 3 equivalent. FOUND: the GEMDOS host dispatcher reads an Fopen name unmasked (PARKED, `## Not
  reconstructed`). THE CODE-REVIEW GATE then found Y's +1-byte halt fix had made both shell frames ODD-sized `uint8_t` locals
  (47 / 23 bytes), which GCC placed at odd stack offsets (`sp+29`, `sp+37`) under word/long accesses — an address error on
  every call on a 68000, green everywhere because the host reads bytes and Musashi runs with address errors off. Fixed as
  `uint16_t` word arrays (the text.c / workstation.c precedent, `FRAME_LOCAL_WORDS`), and given a surface: the oracle shim now
  COUNTS odd word/long accesses (the CPU unchanged for every project) and `rom_bench` refuses an m68k-build row that makes any
  unless its count and its first 8 addresses, in order, equal the ROM's — RED-proved (the `uint8_t` frames back: exactly the
  10 shell rows red, naming address and PC; the PC is the jmp/jsr for a fetch at an odd target); `docs/on-target-execution.md`
  taxonomy 14. The same pass dropped sh_find/rs_readit/rs_load's numerators by one instruction (rs_readit's failed load 0.89
  → 0.88). PARKED (unpinned for this class): odd frame bases that are byte-only today — aes_merge_str `sp@(43)`,
  redirected_read_character `sp@(7)` — red only if a later word access lands on a path a Tier 3 row drives; Tier 1 and every
  other project's target C (asm_twin runs) never consult the counter (TRAP_MODEL.md, "Odd word and long accesses"); and the
  bench blob's frame layout can differ from the shipped ROM image's after inlining — the five-ELF objdump scan was one-off,
  not a standing test.
* **Wave 11 band 2 wave 2 (2026-10-01) — GRAPHICS OVER THE VDI: the rest of gemgsxif with the `$a000` bridge, gemgraf, and
  gemgrlib's non-interactive animations.** Two slice agents (A gemgsxif's rest + the `$a000` bridge + gr_mkstate; B gemgraf
  and gemgrlib's non-interactive part), four reviewers (R1 slice A's C, asm and bridge; R2 slice B's gsx_ layer; R3 slice B's
  gr_ layer and grlib; R4 cross-cutting), two fix agents (FA slice A + the shared hoist, FB slice B): 54 ✅ routines. SLICE A
  (24): the start-up (gsx_init; gsx_wsopen with REAL opens of the physical workstation in all three ST modes; v_opnwk's wrapper;
  gsx_start), the graphics mode and the mouse's interrupt routines (gsx_graphic, gsx_setmb, gsx_setmb_aes, gsx_resetmb,
  gsx_escapes, gsx_wsclose, ratinit, gsx_tick), the mouse form (gsx_mfset; gsx_mfsave/restore through the new `$a000` half of
  the bridge), the save-under buffer and its blits (gsx_malloc/mfree/mret, bb_set/save/restore) and the mouse state
  (gr_mkstate, gsx_mxmy, gsx_button); gsx_mret, ratinit, gsx_mxmy and gsx_button ship as `src/aes/gsxif.S` (3 pinned regions,
  1 relocation). THE `$a000` BRIDGE (`include/aes/gsx.h`'s `gsx_linea_base`): the host `require_cpu_routine(VECTOR_LINE_A,
  LINEA_ROM_DISPATCH)` halts by name on a moved vector, then runs the VDI's linea_init C twin and answers A0 (linea.c's
  answer order hoisted to `vdi.h` as `LINEA_INIT_*` and pinned to the VDI battery's); the target is `.short M68K_LINE_A_INIT`
  with A0 out and d0/d2/a1/a2 clobbered (the dispatcher saves d3-d7/a3-a5). gsx_call moved into gsx.h as one `always_inline`
  (as a function it re-pushed its caller's four arguments; no existing row moved). SLICE B (30): gemgraf's gsx_ layer (clip,
  attributes, lines, boxes, blits, text) and gr_ layer (inside, rect, just, gtext, crack, gicon, box), and grlib's gr_setup,
  gr_scale, gr_stepcalc, gr_xor, gr_movebox, gr_growbox and gr_shrinkbox; five Line-F-free leaves ship as `src/aes/gemgraf.S`
  (4 regions, no relocations); `$fda76e`, `$fe82d6` and `$fe831e` folded; one address register for contrl took gsx_attr's
  cached arm 1.21 → 0.90; the host-slot mask widened to 64 bits (A's slot made 33). THE REVIEW (4 finders): R1 measured
  gsx_mfset at the bar only by its copy loop's spelling (1.0993 own → 0.92), gsx_graphic's held mode above the C's floor
  (76 → 72 cycles), bb_set's logical shift REACHABLE (a right edge past `$7fff`) and its five pointers untagged (RED probes),
  a docstring claiming an unobservable order, and GSX_SHOW_AT_ONCE naming the opposite of v_show_c(1); R2 found gsx_tcalc's
  registered row not the worst (the empty string, 1.097), the index macros spelled in three files, magic literals, a
  mis-spelled mutant and a mutation total merged from two runs; R3 found `shrinkbox-to-once` NOT equivalent (the ROM's run
  ends — it is only long), gr_just's read order and gr_gicon's re-read of its icon unpinned, gr_gicon's row flattering (an
  empty label crosses to `glue`), and gr_box's -32768 thickness REACHABLE; R4 found B's transcription caller machinery a
  copy of wave 1's, door helpers copied, unused imports, `AES_GL_MFORM_AT` misnamed (it is GEM's ad_intin), gr_setup's own
  immediate read as data by unported ROM code, an unguarded host-slot mask width, ROM routine addresses outside addrs.h and
  magic numbers. THE FIXES: FA paired gsx_mfset's copy (two words a pass + the 37th: 1.10 `glue` → 0.92 `net`, shown 0.93),
  spelled gsx_graphic's compare with a split displacement and re-pinned the acceptance at 1.24 (58 → 72, the floor counted from
  the instructions), added bb_set's past-`$7fff` and tagged-pointer cases, a form whose 37 words are all distinct (it killed a
  `mfset-last-stale` survivor the battery's alike last rows hid), renamed GSX_SHOW_AT_ONCE → GSX_SHOW_COUNTED and
  AES_GL_MFORM_AT → AES_AD_INTIN, hoisted INTIN_WORD/PTSIN_WORD/WS_WORD/NO_POINTS/NO_WORDS and one GSX_STYLE_SOLID into gsx.h,
  added `HOST_SLOT_ID_COUNT` with a `_Static_assert` on the mask width (RED: 33 <= 32), moved the AES's three interrupt glue
  routines into addrs.h (`$fed3be`, `$fed3e4`, `$fed426`), and pinned the `$a000` halt message and the LINEA_INIT_* order; FB
  added shrink/growbox `to` over ptsin (+0/+4/+8, a 2,000,000-instruction budget), gr_just's corner after gsx_tcalc, gr_gicon's
  icon re-read and text box over ptsin, registered the two worst rows as they are (gsx_tcalc 1.10 `through`, gr_gicon 1.01
  `glue`), commented gr_box's -32768 (reachable, unpinned) and gr_xor's `$ffff` (unreachable), switched the transcription battery
  onto wave 1's atoms pool and imported the door helpers. MUTATION (strict): slice A 107 — 104 killed, 3 survived (two
  equivalent, `wsopen-no-else` unreachable); FA's 14 — 12 killed, 1 equivalent (`mfset-ad-intin-early`), 1 ABNORMAL (a host bus
  error inside the new corners case, not counted); slice B after FB, one run, 158 — 156 killed, 1 survived (`blt-moff-late`,
  equivalent), 1 ABNORMAL (`attr-no-handle`: the host VDI aborts on the poisoned handle); every `.S` byte-pinned. FOUND: two
  more VDI host gaps reading guest pointers unmasked (vdi_init_wk's arrays, vdi_vr_trnfm's forms), PARKED with the GEMDOS one
  (`## Not reconstructed`).
* **Wave 11 band 2 wave 3 (2026-10-01) — THE OBJECT DRAW PATH: ob_format, far_call, ob_user, just_draw, ob_draw, ob_change.
  BAND 2 COMPLETE.** A read-only SCOPING pass first (the inventory read from the bodies — every routine Alcyon C, so no `.S`
  question; just_draw's type × state matrix with the real data reaching each cell, by a LINK walk over the snapshot's trees;
  the ROM's ob_draw / ob_change measured through the oracle), then three slice agents — U and J in parallel, O once J was
  green — three reviewers (R1 slice J; R2 slice U and cross-cutting; R3 slice O) and one fix agent: 6 ✅ routines, 263 tests in
  four batteries (`test_aes_obuser.py` 49, `test_aes_just_draw.py` 52 and `_staged.py` 84, `test_aes_ob_draw.py` 78), 43 Tier 3
  rows (ob_format 7 `through`, far_call 1, ob_user 1 `through`, just_draw 17 / ob_draw 9 / ob_change 8 (V) `net`). SLICE U
  (`src/aes/obuser.c`): ob_format, far_call and ob_user, `test/aes_obuser.py` the shared USERDEF door (a 68000 routine logging
  the 30-byte PARMBLK into a compared log and answering D0, with its host twin); `staged_call.h`'s call_alcyon_pointer now
  ANSWERS D0, held live across the target `jsr` by an empty-asm output so sh_find stays byte-identical (`cmp` of the .o). SLICE
  J (`src/aes/objdraw.c`): just_draw over its ROM frame (one 48-byte host slot in `link #-48`'s layout; the jump tables
  `$fefba0`/`$fefbcc` as two `switch`es with their fall-throughs), every type × state cell over the snapshot's own trees or
  staged on a real object, the packed-longword sites through one helper family (`packed_add`/`packed_sub`/`pair_high`/
  `pair_low`, hoisted by O into `m68k_idioms.h`), the frame staged STALE on both shores. SLICE O (`src/aes/obdraw.c`): ob_draw
  and ob_change over their frames, and THE ALCYON ENTRY (`src/aes/obdraw.S`): ob_draw hands everyobj just_draw BY VALUE
  (`$fea08c`), and a target ob_draw handing it `$fe9a88` would run the ROM's just_draw inside our build — which the (V) bench
  REFUSES (RED-proved: 248,590 cycles in the AES's spans, refused by name) and which a rebuilt ROM cannot owe. The entry repacks
  everyobj's 10-byte Alcyon frame into the GCC call (image base 0, each word sign-extended into its slot); it is target-only
  glue (`atari/target.mk` ALCYON_ENTRY_SOURCES, filtered out of TRANSCRIBED_SOURCES so the `.globl` pin stays exact), Tier 3
  counts it as glue (`tier3.ALCYON_ENTRIES`, T→G), `test_transcribed.py` pins its `.globl`s to that list. Its four mutants,
  judged by Tier 3's second differential (no host surface sees it): x/y swapped, the object pushed as x and image base 4 RED;
  the three `ext.l` dropped GREEN — equivalent BY GCC's design (R3: the m68k callee re-extends an `int16_t` from the slot's
  low word at every -O level), kept as the correct promotion. THE REVIEW: R1 (just_draw) proved J's "tree 2's TEXT has no
  writer" ROM finding WRONG — sh_draw (`$feada0`) stores the shell's command through ad_pfile (`$c7a2` = tree 2 obj 2's ob_spec,
  TEDINFO `$d18c`) at `$feadca` right before its ob_draw; the -1 is the resource's placeholder until the first launch, so TEXT is
  NOT app-only (RETRACTED, here and in AES_MAP) — and found five non-equivalent survivors J's 114-mutant sweep had passed (every
  snapshot colour word has border colour = text colour; the only negative-thickness BOXTEXT carries no state; the menu's titles
  are exactly as wide as their labels; no CHECKED case moved ad_intin), a CROSSED h=0 case whose borrow carried back (y ≠ 0),
  and a TITLE+SHADOWED row in black that drew like STALE. R2 (ob_format and cross-cutting) found te_just's WORD compare
  unpinned (0/1/2 only — `$0101`, 5, -1 kill two survivors), the priced worst row a case choice (a FULL 38-character path, est.
  0.88), and duplication across slices (two `object_word`s, three spellings of "tree N of a resource", copied `tedinfo` /
  `string_at` / REGISTER / loggers / raw-text seeders / `real()`, PARM missing from `aes.RECORDS`, literals the headers name).
  R3 (ob_draw / ob_change, C faithful instruction by instruction) found O's desktop-band case DEAD — its TEXT lay wholly above
  the snapshot's clip, so te_ptext was never read and any string passed — and THE UNREACHABLE FONT MACHINE: J's default
  `IBM_FONT_CACHED` staged gl_font 3 over the VDI's SMALL face, a pair (3, small) no AES path makes (gl_font's two writers,
  gsx_start `$fdaace` and gsx_tblt `$fdad4a`, keep it true to the VDI), so every IBM label over the default machine drew in the
  6×6 font, and one case's "screen changed" evidence held only because of it (in the real font the title redraws the
  snapshot's own pixels). The lesson: a machine is DERIVED from a ROM run, never poked — a poked cache can describe a state the
  machine cannot reach, and every differential over it still passes. R3 also recorded the D0 ob_draw / ob_change leave for the
  bindings `$fde2fe` / `$fde32c` (`## Not reconstructed`). THE FIX (one agent): IBM_FONT_CACHED re-derived as the write-delta of
  the ROM's own gsx_tblt(IBM, 0 chars) (`case.written_by`, the new helper `continued_from` now shares), the whole-screen-clip
  machine built OVER it, a permanent pin that the cached font draws the VDI's own IBM face, the menu-title case split into
  "redrawn in place = the snapshot's pixels" and "drawn elsewhere"; the desktop band staged as sh_draw leaves it in both J and
  O (`AES_AD_PFILE` `$c7a2` in aes.h) plus R3's dead-staging probe kept as a pin; R1's five survivors and R2's two as permanent
  cases; the full-path ob_format row (0.87, the new worst); one `object_word`, one `aes.resource_tree(index, image,
  application_global)`, `isr.REGISTER` / `answer_d0` / `frame_long_logger`, one raw-text seeder, PARM in `aes.RECORDS`; obdraw.S's
  REGISTERS line widened (D0-D1/A0-A1 with the C core); and the wave-2 files' inline `pair_high`/`pair_low` folded (gsxif.c,
  grlib.c, gemgraf.c — byte-identical, `cmp` of all 9 objects under three flag sets). The J label rows' whole-run counts moved
  with the real font; no (V) gated ratio moved and no row outside wave 3 did. MUTATION (strict), honestly as two runs: the
  authors' sweeps — J 109/114 (5 equivalent), U 32/32, O 41/43 with 2 ABNORMAL (`last-nil`, `last-head`: everyobj's guard aborts
  on the full battery; each KILLED cleanly by `-k scroll`) — and the reviews showing J's true tally 109/114 PLUS 5 non-equivalent
  holes (R1) and ob_format 2 more (R2); the fix re-run, all 209 over the fixed batteries: 199 KILLED, 8 SURVIVED (all equivalent:
  J's clip-w-only, clip-h-only, image-row-16, marks-always, marks-low-byte; R1's set-aside label-chars-byte,
  userdef-state-low-byte, shadow-after-neg-signed), 2 ABNORMAL (O's two, KILLED by `-k scroll`).
* **Wave 12 band 3 wave 0 (2026-10-02) — THE EVENT DOOR, the object editor, the window library's pure half.** A read-only
  SCOPING pass first (the band-3 inventory read from the bodies: ≈16 KB, 87 routines unported; each classified by how it
  reaches the scheduler — LOOP, ONE call, or none — measured through the oracle; the band-4 code band 3 reaches named: eight
  door entries and five non-blocking leaves to port in band 3; the slices and waves F ∥ O ∥ W1, then W2 ∥ G, then M, then S;
  the map's errata), then three slice agents in parallel, four reviewers (R1 slice F; R2 slice O; R3 slice W1; R4
  cross-cutting) and three fix agents (FD ∥ FO, then FW): 38 ✅ routines, 121 Tier 3 rows (gr_stilldn 7, gr_watchbox 4,
  ap_sendmsg 3, ct_mouse 4; the object editor 48; the window library 55). SLICE F — THE EVENT DOOR + pilots
  (`include/aes/evdoor.h`, `src/aes/evdoor.c`, `test/aes_event.py`; `src/aes/grwait.c`, `apmsg.c`, `ctrl.c`): one wrapper per
  door entry keyed by ROM address — on target an INLINE Alcyon call (a `.S` call-out repacking GCC's slots measured gr_stilldn
  at 1.84; the inline frame 1.09, then 1.04 once a constant-zero argument pushes the already-zero A1), on the host a nested
  oracle run of the ROM's routine over the candidate's image, the Line-F hop checked first; the BIOS trap's register save
  under the keyboard poll (`$8de..$905`, the caller's registers) the one thing that differs by nature, dropped by name in
  Tier 1, priced rows moving savptr into the stack band; door cases unpoisoned (the pass inverts the fork queue / CDA / EVB
  links: measured), stale staging their stand-in. Tier 3's letter (E) was taken, so the mechanism is (EV): our run WATCHED at
  the door's entries (the kit's `RomBench.measure(watch=)` + `emu.bench_door_arm`, its own commit), each door call a window
  off the ROM's own cycles, AES cycles outside a window refused — RED both ways (a delayed body OVER while the whole run stays
  ~1.0; an unwatched run refused) and five target mutants of the door judged by Tier 3's second differential. SLICE O
  (`src/aes/obedit.c`): ob_edit (812 B, not the inventory's 1,942) and ten gemobed helpers, Alcyon C over their own read /
  write order, three host slots, every EDCHAR case from the ROM's own EDINIT; ob_stfn 1.17 → 0.95 by holding the inlined
  template in a register (`CURSOR_BARRIER`). SLICE W1 (`src/aes/wmlib.c`): gemwmlib's non-blocking half, 23 routines, every
  machine derived from the ROM's own window chain (wm_create → wm_open → wm_set: move, sliders, sizes, the drawing hold,
  NEWDESK), every D0 the desk's bindings store modelled (wm_delete's and wm_get's address leaks, wm_calc's height);
  w_bldactive's -1 test kept apart from its body (1.15 → 0.12). THE REVIEW. R1 found THE FOUNDATION FLAW: 4 of gr_stilldn's
  9 priced rows stood on ev_multi answering "no event" — under the snapshot's indisp = 1 the dispatcher `dsptch` (`$fe387c`)
  is a bare `rts`, so ev_mwait's blocking call (`$fe40de`) RETURNED where the machine would block; a process calling ev_multi
  always has indisp 0 (switchto clears it on every switch in), so that outcome is unreachable — and NESTED_RUN_INSNS, the
  slow-path case and Tier 3's RED-proof row all stood on it. And `pd0_running()` was a POKED hybrid: acancel over
  leaf_machine's poked rlr left PD_STAT 1 and PD0 on the not-ready list, chaining PD1 into the ready list (`[PD0, PD1]`); the
  "parked" machines ran PD0 while it was parked in its own evnt_multi (ap_sendmsg "to PD0 parked" was PD0 sending ITSELF a
  message, sender word 0). R1 also proved F's mutation total OVERSTATED: the child-process refusal cases bound the hook into the
  SHARED `build/` lib while the child called the PRIVATE mutant lib, so 13 "kills" were segfaults (rc -11) that fail with no
  mutant at all — honest 53 K / 8 S, three of the survivors REAL holes (gr_watchbox's rectangle, x/y order and leave flag were
  never observed: ev_multi's rise is satisfied whatever MOBLK it gets) — and that (EV) never checked the ROM's event-layer
  cycles against our windows. R2 (slice O; no C divergence, instruction by instruction) found the "unobservable" refused-key
  `start++` OBSERVABLE (an application's objc_edit index of `$7fff`: the scan's word wraps and the fill runs — a FALSE
  EQUIVALENT), the stretch's `copied > 0` unpinned (a 255-character validation string), one unmeasured poison opt-out, the
  Tier 3 rows below the worst (80 placeholders: find_pos 1.058, ob_stfn 1.035; STANUM; 'N'), three pointers never tagged.
  R3 (slice W1) found WM_MAX_DEPTH pinned only to ≥ 4 (depths 4 and 5 survive), 19 untagged pointer cases, the mutation total
  reproducible only with `-x` (strict: 149 K / 8 S / 5 ABNORMAL — real FAILs, then an abort or a 5-minute hang), the held
  w_move's D0 "pin" circular (the ROM leaves the caller's D0), and reconciled W1's "ob_draw never returns seven levels down"
  with band 1's everyobj divergence counted from the start object. R4 (cross-cutting) found wmlib's four frames not
  `_Static_assert`ed to their host slots (RED: a halved slot built and passed), DERIVATION_INSNS's stale justification and
  unpinned margin, duplicated helpers (`stored_nothing`, frame packing, retyped WF_* field numbers — field 13 had three names),
  `aes.line_f_call_sites` scanning the AES text per name at import (1.75 s per process), the addrs.h wm_* rows without "read:",
  and the AES staging window full. THE PRINCIPLE (the fix list, binding): a case may only stand on a state the real scheduler
  produces; a nested run that reaches the blocking dispatcher is REFUSED ("would block"), and a running process is DERIVED —
  the event it waits for delivered, the ROM's own scheduler run — never rlr / indisp / PD_STAT / the lists poked; a derivation
  impossible within one oracle run is refused with its measured reason. THE FIXES. FD: the nested run stops at `dsptch` and
  refuses by name (a kit addition: `emu.run` reports `checkpoint` through a new shim export `osh_final_pc`); 2 of the 4 rows
  re-staged on a satisfied event, 2 turned into child-process "would block" refusals, the "PD0 parked" gr_* rows removed;
  NESTED_RUN_INSNS 20,000 at a pinned margin of 20 over the deepest reachable call (ap_rdwr handing to PD0's parked wait, 933);
  `aes_event.machine(woken=…)` = an event delivered, disp's loop `$fe4dda` run until the woken process leaves its evnt_multi at
  `$fe6c5c` (Return wakes PD0 in 1,972 instructions, the left button 1,412, the mouse on the menu bar wakes PD1 in 1,539),
  then the ROM's gsx_moff — a scheduler-invariants test RED over the old poked mix; ap_sendmsg "to PD0 parked" now sent BY PD1;
  the child binds into its own lib (RED: the old binding rc -11); every door call's frame compared with the ROM's own call's
  (watched at the entries — killing R1's three holes), and Tier 3's (EV) watching the ORIGINAL too, windows and frames equal
  both sides (RED: a window one cycle dearer, a ROM timer +1); DERIVATION_INSNS' margin enforced; one cached Line-F call index
  (1.76 s → 0.03 s, identical answers for all 280 names); the staging window 8 KB → 16 KB with every claim at its old address;
  GSX_SHOW_AT_ONCE one name. FO: the `$7fff` case landed in 1.1 s (the save-under buffer staged as placeholders: the ROM run
  35,836,288 → 1,944,393 instructions, budget re-measured by the test), the 255 / 256-character cases, the opt-out dropped,
  the worst rows registered (find_pos 1.06, ob_stfn 1.04, instr 0.98, check 0.59, ob_edit 0.80), the tags, one INDIRECT /
  EDITABLE / stored_nothing. FW: an 8-box desk (six levels below object 1) plus a 6-box one beside it (the 8-box tree alone
  turned the wrong-root mutant ABNORMAL), R3's 19 tags folded in, the held arm asserting `stored_nothing` and the caller's D0,
  four `_Static_assert`s (RED each), one W_BORDER and one WF_RESVD name, `aes_event.frame_of` / `window_created` the single
  source, the window machines over the scheduler's running PD0 (pinned: rlr == [PD0], indisp 0); objects byte-identical.
  MUTATION (strict, a private `.so` per mutant, NO `-x` credit), honestly as three runs: the authors claimed F 59 / 61 killed,
  O 132 / 136 (4 "equivalent"), W1 154 / 160 (6 equivalent); the reviews showed F at 53 K / 8 S (13 kills were segfaults of a
  mis-bound child), O's `start++` a false equivalent plus two unpinned arms, W1 at 149 / 8 / 5 ABNORMAL without `-x` plus two
  real depth holes; the fix re-runs on the final code — F host 61: **59 KILLED / 2 SURVIVED (equivalent) / 0 ABNORMAL**, F
  target (Tier 3) 7: **6 KILLED / 1 SURVIVED** (equivalent: no caller passes a non-zero second rectangle, timer or message);
  O 143: **139 KILLED / 3 SURVIVED (equivalent) / 1 ABNORMAL** (bus-find-first: SIGSEGV in all three attempts, not counted
  killed); W1 162: **156 KILLED / 6 SURVIVED (equivalent) / 0 ABNORMAL**.
  Code-review gate (4 finders + verifier): the button pressed through the VDI's mouse interrupt (AES, VDI and interrupt state
  agree — the glue-only press was a state no hardware holds); interrupt-level derivations stand on no lever; every
  process-level derivation refuses a dsptch; the child binds the VDI vector too and refuses ANY exception (one had escaped
  the ctypes callback and read as "served"); gr_watchbox's second pass pinned to its wait; the door watches exact entry PCs
  (kit stop sets); the general ev_multi arm removed (a compile error until a caller needs it). Re-sweep after the child fix:
  F host 62 → **60 KILLED / 2 SURVIVED (equivalent) / 0 ABNORMAL**, target 6/6 KILLED.
* **Wave 12 band 3 wave 1 (2026-10-02) — the window messages and update, the drag loops, the menu library.** Two slice
  agents in parallel, four reviewers (R1 slice W2; R2 slice G; R3 the shared machinery; R4 cross-cutting), a fix list with
  one binding DECISION, then three fix agents (FS first, then FG ∥ FW2) and a finishing agent. Result: 29 ✅ routines and
  91 Tier 3 rows (W2 45, G 46), every one within the bar.
  - SLICE W2 (`src/aes/wmupdate.c`, `wmupdate.h`, the target-only `wmupdate.S`): 13 routines and four door entries
    (tak_flag, unsync, ev_block, ct_chgown). draw_change hands everyobj newrect BY VALUE. On target that is an ALCYON ENTRY
    for newrect AND one for mkrect: before it, our target newrect handed the ROM's mkrect, which is ROM AES code inside our
    build, and (V) refuses that. newrect's two cut rows were re-priced honestly as a result (0.81 → 0.67, 0.89 → 0.72).
  - W2 found the UNBALANCED END_UPDATE deadlock (a ROM finding, pinned on a ROM-produced state) and left the hand-over of
    the lock to a waiting process unpinned. Four overlapping-window arms were left over the bench's cap (Tier 1 only).
  - SLICE G (`src/aes/grdrag.c`, `mnlib.c`): the drag loops and the menu library, 16 routines plus gr_draw / gr_xdraw /
    `$fe86c2` folded. post_button joined the door, and ev_multi gained its two-rectangle target shape. The door stopped
    laying back the Line-F mask word `$cc44`: measured, 19 Tier 3 companions of routines that make their own masked return
    after their last door call failed with it laid back. The child binding gained just_draw.
  - G left "every state after the first pass" UNPINNED as "needing the mouse or button to change inside one run".
  THE REVIEWS.
  - G's COVERAGE WAS WEAKER THAN CLAIMED (R2). The unpinned arms were a harness limit, not a machine limit. R2's prototype
    delivered the ROM's own ISR at the k-th door entry on both sides. With it, mn_do reached MN_IN_MENU and exited with an
    item chosen, byte-identical, and four real mutants of those arms that pass the whole battery died
    (exit-title-item-swapped, in-menu-button-inverted, exit-no-restore, exit-item-redraw). The drag steps and both busy
    loops were reachable the same way.
  - Three of G's "equivalents" were FALSE. bar-height-wchar: high resolution is derivable from the ROM's own gsx_wsopen.
    down-depth-1 and do-find-depth-2: an item with a child is ordinary resource data. do-item-not-cleared was reachable by
    interrupts.
  - Every G machine ran with the cursor HIDDEN, so xdraw-no-cursor (gr_xdraw's moff/mon dropped) survived. pd_nameit's
    finding and comment were wrong: strscn writes no NUL. rc-no-bus-flag was an invalid mutant.
  - R1 (W2): survivor 96 was a FALSE equivalent. rc_union writes INTO `old`, so a far zero-height move redraws more.
  - R1 measured the four "Tier 1 only" arms as priceable over title-bar windows. R4 found that the "their arms are priced
    below" comment was false: topped's redraw arm, the old top's w_cpwalk and wind_set(13, 0)'s release were priced by no
    row, shown by an llvm-cov run of every companion.
  - R1: all 12 of W2's ABNORMAL mutants were KILLS. Serial runs lost them to the first abort, and drawing cases CAN run in
    a child.
  - R1: ev_block's "answered" door row stood on an UNREACHABLE state. Its only caller hands code 4 after tak_flag refused,
    and amutex refuses again. The unsync hand-over looked derivable from ROM runs alone.
  - R1 recorded the target D0 divergence under a held lock.
  - R3 (shared): the nested-run cap was broken by mn_do's two-rectangle ev_multi (1,237 × 20 > 20,000) while the pin
    checked the wrong call. The host-slot mask was at 60 of 64 bits. The default child binding still dropped walker calls
    silently. The `$cc44` comment overstated (only NON-EMPTY masks are written). ev_block's `ad_windspb` read was unpinned
    (equivalent).
  - R3 ran the RED W2 had not: with the Alcyon entries bypassed, every draw row is REFUSED by the bench (19,060 cycles in
    the AES's own spans).
  - R4 (cross-cutting): "refused where the ROM blocks" was spelled four times and the child-first guard twice. The routine
    handed by value was copied three times (C), and so was the walker map (Python). `_cached`'s cache never hit.
    `AES_ROM_GR_WAIT`'s comment had the two-box rule wrong, and mnlib.h carried a "band 4" label.
  - R4: import cost — test_aes_wm_update's own import was 5.2 s (40 ROM runs for `settled_mask_word`, 259 merges), and
    test_aes_event now imported the batteries at module top.
  THE DECISION (the fix list, binding): adopt interrupt delivery at door entries as shared machinery. It obeys THE
  PRINCIPLE because:
  - an interrupt arriving while a process is inside an event call is a REACHABLE interleaving;
  - its effect is a ROM-run delta of the ROM's own ISR, never a poke;
  - both sides receive it at the same door-entry ordinal, and the frame comparison and (EV)'s window equality still hold;
  - a RED proves the injection is applied on both sides.
  THE FIXES.
  - FS (shared):
    - `aes_event.interrupted`, with one correction measured: an `emu.run` inside a watched run's stop derails it, so each
      interrupt is computed with no run in flight and laid in at the entry. RED on each side and one ordinal off.
    - the child's register hook always bound: walked routines are served or refused BY NAME (exit 5).
    - the nested-run margin checked at run time, the cap 30,000.
    - the host slots' held flags an array of bytes; one `ALCYON_ROUTINE` (objects identical); one walker map.
    - `refused_where_the_rom_blocks` and `returns_in_a_child` in aes_event; `shown_machine`; moves that keep a held
      button; aes_event imports no test module.
  - FG:
    - mn_do's ten later-pass sequences and nine drag sequences through interrupts.
    - an item with a child staged from the desk's spare objects (a G_BOX: the first version's blank G_STRING let
      down-depth-1 survive).
    - cursor-shown machines; pd_nameit's nine-character case; the conventions.
    - a high-resolution workstation built from the ROM's gsx_wsopen + gsx_start.
  - FW2:
    - five rows priced over title-bar windows and wind_set(13, 0)'s release over an area (0.70–0.75).
    - survivor 96 killed; ev_block's answered row dropped (`NEVER_ANSWERED`).
    - unsync's HAND-OVER PINNED (`aes_event.parked`): PD0 holds the lock and parks, the screen manager queues on it, and
      Return wakes PD0. The door refuses it as a YIELD.
    - 14 drawing door users guarded in a child; the import at 2.4 s with 45 rows.
    - THE WOULD-BLOCK / YIELD SUBSTRING BUG: the core's generic halt line names "a call that would block … or yield", so
      `"would block" in stderr` passed a yield as a block (measured: the RED did not raise). `BLOCKS` / `YIELDS` now match
      the dispatcher's own words.
  - FINISH:
    - the high-resolution mn_bar case DROPPED as an unreal machine. A composed low/high workstation writes 216 B below the
      screen base in a 160 stride, over MASKed boot-noisy bytes (the noise test went red). A real resolution switch is not
      derivable, so bar-height-wchar is unpinned again.
    - the cap raised to 40,000 from mn_do's interrupted first ev_multi (1,697, pinned exactly), which pins pass 1's
      interrupted wait.
    - every block / yield match spelled by the dispatcher's words.
    - the Tier 3 pricing of interrupted rows NOT landed. Its blocker is measured: it needs a kit change, so it was deferred
      (`## Not reconstructed`).
  MUTATION (strict: a private `.so` per mutant, xdist, no `-x`), honestly:
  - W2 claimed 123 KILLED / 14 SURVIVED / 12 ABNORMAL of 149. R1 measured **136 / 13 / 0** with probe 96 and the child
    cases, and FW2's re-sweep on the final code confirmed **136 / 13 / 0**: the 13 equivalent, `## Not reconstructed`.
  - G claimed 142 / 9 / 0 of 151, the 9 "equivalent". Honestly, of 150 valid mutants, 4 of the 9 were killable, and 5
    mutants R2 wrote against the "unpinned" arms survived the battery.
  - FG's re-sweep of 169 (150 + R2's 6 + 13 on the newly reached arms): **165 / 4 / 0**. The finish's dropped
    high-resolution case brings bar-height-wchar back to SURVIVED, so it stands at **164 / 5 / 0** (derived, not
    re-swept): 3 equivalent, door-post-words-swap latent, bar-height-wchar unpinned.
  - G target (Tier 3): 8 — **6 KILLED / 2 SURVIVED** (post-words-swap; post-no-d2-clobber, nothing live in D2).
  - The finish's 2 logic changes (the cap, the delivery in `rom_s_first_call`): **2 KILLED**.
* **Wave 12 band 3 wave 2 (2026-10-02/03) — the forms and the alerts; interrupted rows priced.** A foundation agent (K)
  first, then two slice agents in parallel (M1 the event-free half, M2 the forms that wait), four reviewers (R1 K and
  M2's machinery; R2 slice M1; R3 slice M2; R4 cross-cutting), a fix list, then two fix agents in parallel (FK the kit and
  the shared machinery; FM the forms). Result: 16 ✅ routines, 81 Tier 3 rows (K 4, M1 20, M2 51, FM 6), every one within
  the bar; no pre-existing row's numbers moved.
  - K (FOUNDATION + KIT, the kit's own commit): the bench run's own write ledger (`osh_run_bench` clears it after its entry
    stores; `emu.bench_writes`); `rom_bench.watched_original` and `RomBench.measure(original_watch=)`, the original run as
    a watched bench run entered as `emu.run` enters it, every vet live. In the project: the `delivered` ninth field,
    deliveries laid on all four of a row's runs and in the snapshot's sweeps, a call reaching dsptch refused by name on
    every watch; the 18 returning interrupted cases of the time through the bench's second differential; mn_do's,
    gr_dragbox's, gr_slidebox's and gr_rubwind's worst interrupted rows registered (0.63 / 0.80 / 0.75 / 0.80); keys on the
    in-place delivery path (`key`, `typed`) in ONE watched run, set aside and continued at each entry (linear where it was
    quadratic). Found on the way: `run_watched` entered with the previous run's registers, so the BIOS trap save under
    the keyboard poll differed between runs (red under xdist); now seeded and pinned.
  - M1 (`src/aes/fmlib.c`): fm_strbrk, fm_parse, fm_build, find_obj, fm_inifld, fm_keybd, dq, fq — 100% regions, lines
    and branches (64/64) under llvm-cov. fm_strbrk has no bound on lines or buttons; button buffers are 11 bytes against a
    31-character cap.
  - M2 (`src/aes/fmdo.c`): fm_button, fm_do, fm_dial, fm_alert, fm_show, eralert, fm_error and the bell; ev_button the
    sixth door entry; K's `Typed` generalised into `Waits`; `double_click` through the VDI mouse ISR. The bell is BIOS
    Bconout by `trap #13`, not the DOS glue the brief named (`bios_trap_constant_char`: the register shape had cost 1.09).
  THE REVIEWS.
  - THE REAL DIVERGENCE (R2): fm_strbrk's 5th button or 10th line stores at `$ff1100` — object 11, tree 2's object 1,
    ABOVE RAM. The oracle drops the store (an ST loses it or bus-errors); the host C wrote it into the image: RED,
    `0xff1100: oracle=0x00 cand=0x45`. M1's own `INDEX_STEERS_THE_PASS` comment had seen this walk ("where the oracle's
    store is lost and the host's lands") and opted the pass out rather than refuse it; and R2 measured the opt-out wider
    than its measurement (15 of 18 direct cases pass poisoned).
  - STALE CHIP STATE ACROSS BENCH RUNS (R1): `watched_original` installed no PSG / named-hardware seed, so it read the
    previous run's — the printer's Bcostat answered $0 or $ffff by which case ran before, and the refusal `emu.run` makes
    ("nothing declared") disappeared. `parked` entered with the previous run's registers (94 bytes of its machine
    differed). `Waits` checked its entry only on an ordinal's first sight and counted `pending` across runs (R1, R4: a
    schedule handed to another routine laid a key at a non-ev_multi call). Two spellings of the watched entry; tier3.txt's
    cost cells ran together on 29 rows.
  - THE HAND-WRITTEN INTERRUPTED LIST (R4): K2's "every returning interrupted case gets the second differential" was a
    list over three modules; M2's **35** returning cases (fm_do 27, fm_alert 7, eralert 1) were not on it. All 35 passed
    when R4 ran them — coverage, not a divergence. The deliveries were derived twice per registered row (+3.4 s of
    test_boot_snapshot import per worker).
  - FALSE "UNREACHABLE" (R3): fm_error's `1` answer is reachable — an application's form_alert(-1, …) leaves DEFAULT on
    a message line of the shared alert tree, and Return in any later alert then answers -1. Two mutants survived both
    batteries on it (fm_error `return 0`; fm_alert `default_button > 0`).
  - FLATTERING ROWS (R3): fm_do's worst was picked (0.70), not measured — every row typed into an EMPTY field, and the
    "per-key shapes, each priced" had no rows; with the path field filled as fs_input fills it, 0.75. The bell's 1.06 was
    not its worst (1.07 with the console mid-escape; the excess is the d2/a2 save round `trap #13`).
  - Also: fq's choice of gl_cda over gl_kowner unpinned (a surviving mutant, R2); the fm_keybd errata misread `$fefa64`
    (R2); eralert's ">6 maps into 0..6" reason wrong (R3: the critic keeps ~error's high byte); icon digits past 3
    unstaged; the over-cap alert shape unnamed; frame-word helpers written three times, flag masks and the fm_keybd
    answers redefined per file, test helpers re-implementing `aes.parent_of`, `typed`, the ROM's ob_offset; magic numbers
    in the new tests (R4).
  THE FIXES.
  - FK: one chip declaration (`emu.install_chip_seeds`) and one entry spelling (`rom_bench.original_entered`) under every
    bench entry of ROM code, RED at the kit level; `parked` seeded (RED: two stale register files, one machine); `Waits`
    checks its entry at every call and counts per run; THE SECOND DIFFERENTIAL BY CONSTRUCTION — `aes_event.interrupted`
    runs it for every returning case (56 today), the hand list deleted; deliveries derived once per registered row (32
    deliveries runs at import → 16); tier3.txt's cost columns sized from the data; `_registered_runs` refuses a delivered
    row; README's stale line.
  - FM: the bus accessors refuse BY NAME a store at or above `ST_RAM_BYTES` (five-button and ten-line fm_parse cases, the
    bound itself pinned both sides; no existing case wrote there); `INDEX_STEERS_THE_PASS` re-measured after the refusal
    and made per case (11 of 18 steer above RAM and refuse; 7 run poisoned); fq with the keyboard handed to PD1 by the
    ROM's own ct_chgown; fm_error's `1` and the negative default as permanent cases (the machine the ROM's own fm_alert
    run leaves); the long-path fm_do rows (0.75 ×3, 0.72) and the mid-escape bell rows (1.07 ×2) registered; icon digits
    4, 5, 6, 9, ':'; the over-cap alert named; the flag masks in `objects.h`, one frame-word helper (objects byte-identical,
    106 target objects compared section by section); the test duplication and magic numbers.
  MUTATION (strict: a private `.so` per mutant, xdist, no `-x`), honestly:
  - K: 29 — 28 KILLED / 1 SURVIVED (the derivation run's register seed: equivalent, the compared replay is seeded) /
    0 ABNORMAL; its 7 kit mutants all KILLED.
  - fmlib.c: M1 claimed 60 / 3 / 0 of 63 (first pass 55 / 5 / 3). R2's fq-kowner SURVIVED it. FM's re-sweep of 73 (+R2's
    10): **66 / 7 / 0** — following-unsigned equivalent; build-no-min and build-row-unsigned UNREACHABLE (not equivalent:
    each needs the 5th button / 10th line, which faults first); R2's four equivalent on every reachable machine.
  - fmdo.c + evdoor.h: M2's final 102 / 4 / 0 of 106 (first pass 98 / 8 / 0). R3's two SURVIVED it (the false
    unreachable). FM's re-sweep of 108: **104 / 4 / 0**, the four equivalent.
  - The store-above-RAM refusal: 8 — **5 KILLED / 3 SURVIVED**: ram-word-as-byte equivalent (a word store is even after
    the odd-address refusal); ram-long-unchecked and ram-long-as-word UNPINNED (`## Not reconstructed`).
  - FK: 19 — **17 KILLED / 2 SURVIVED**: the chip declaration dropped from `parked` and from `_continued_at`, equivalent
    today and unpinned (`## Not reconstructed`).
* **Wave 12 band 3 wave 3 (2026-10-03) — the file selector; a case's own budget, sessions priced by their slices.** A
  foundation agent (K) and a slice agent (S1, the event-free half) in parallel, then S2 (fs_input) on both; four
  reviewers (R1 K's machinery and S2's additions to it; R2 slice S1; R3 slice S2; R4 cross-cutting: cost, bands,
  duplication, conventions); a fix list; two fix agents in parallel (FP performance and mechanism; FT tests, rows and C
  conventions). Result: 11 ✅ routines and one ⚠️, 74 Tier 3 rows (K 5, S1 29 then 32, S2 27 then 37), every one within
  the bar; no pre-existing row's numbers moved. BAND 3 IS COMPLETE. The kit is untouched.
  - K (FOUNDATION, `test/aes_event.py` + `bench/tier3.py`):
    - THE PER-ROW BUDGET. `DERIVATION_INSNS` (1.5 M) and its margin of 5 are untouched; a case that needs more passes
      `budget=`, which is also its run's cap, held by name: above the default, fitted by the margin, and — for a run that
      ended — not stale (`DERIVATION_STALE` = 2), so 5N <= B <= 10N. A registered row records it (`InterruptedRow`).
      RED on fm_do's 38-key session (728,664 instructions) and on the ROM's own fs_input (635,277), each refused under
      the default in the default's own words.
    - SLICE PRICING. Measured first, and it changed the design: door calls alone do not cut fs_input under the cap — its
      first door call comes after 354K–371K instructions — so a slice end is an ARRIVAL both shores make at one PC:
      `door_call`, `trap_taken` (a VDI or GEMDOS call outside any door call), `ENTRY`, `RETURN`. Both shores run the
      whole session, marked at the two ends; the row is the difference of the marks; our memory must equal the ROM's at
      both, after the same door calls (`vet_the_marks_agree`); a slice past `SLICE_INSNS` (200,000) is refused.
    - Shown on the ROM's own fs_input as oracle on both shores (eight shapes, 5K–185K, summing to the whole) and, C
      against ROM, on fm_do's 38-key session: five rows, 0.67 / 0.68 / 0.76 / **0.77** the last character typed / 0.71 —
      fm_do's new worst (it was 0.75).
  - S1 (`src/aes/fslib.c`, `gemdosif.c`): fs_start, fs_back, fs_pspec, fs_active, fs_1scroll, fs_format, fs_sel,
    fs_nscroll, fs_newdir, dos_snext and the Cconout glue. Machines the ROM's own fs_input stopped at each routine's
    entry over a staged disk and REAL GEMDOS; GEMDOS REPLAYED for Tier 3 (a staged `trap #1` handler with a ledger, the
    script derived from the ROM's own GEMDOS call by call). dos_sfirst's tail extracted as `search_found`, which
    dos_snext shares as the ROM does (dos_sfirst's rows unmoved); `gemdos_trap_word`, the function-word-only trap shape.
    The scoping's "dos_snext shares `$fe3c28`" was wrong: it is dos_sfirst's tail `$fe3a2c`.
  - S2 (`aes_fs_input`): the selector run whole as SESSIONS — 75 returning and 20 cut short at a wait at first, held at
    the end, at the wait, and by every VDI call in order; real GEMDOS on both shores for keys typed ahead and the three
    no-memory arms. Priced as 24 slices of four sessions plus the three no-memory rows. `declare_child_doors` (the
    child's `trap #1` door), `stopped_at(budget=)`; the AES window to 24 KB; K's survivor b21 pinned by the session that
    blocks with nothing delivered.
  THE REVIEWS. Verdict of all four: THE C IS FAITHFUL TO THE ROM EVERYWHERE — R2 and R3 read it instruction by
  instruction and R3 ran 37 more sessions C against ROM; every finding was a test, pricing, cost or convention defect.
  - WHAT WAS PRICED (R1). fs_input's proposed worst, 0.84, depended on where the Return row's cut fell: the selector's
    PUT-AWAY (fm_do's last unsync to the return) measures 0.88 own / 0.98 with thunks in every session, averaged down
    to 0.81 behind fm_do's own key handling. And the registered slices PARTITIONED NO SESSION: 49–93 % of each session's
    ROM instructions were in no row, and nothing said so (no gap hid a row over the bar; the mechanism could not show
    it). A budget could be declared over a run the default covers (the rule tested the declaration's size, never the
    run's need — K's own positive case sat in that window, its `budget=` really raising `emu.run`'s cap); `stopped_at`'s
    budget was not pinned as the cap (a surviving mutant); trap arrivals are matched by ordinal and memory, never by
    count. K's five ABNORMAL mutants were shown honest kills (armed after collection: each KILLED by 7+ tests).
  - THE EVENT-FREE HALF (R2). Four holes, each a mutant passing all 275 cases and a real-data case that kills it: the
    folder test is a BIT test and no staged folder carried a second attribute bit; the 100-name cap was never run under
    a spec that filters (names KEPT against names SEEN); fs_1scroll's arrow and fs_sel's row are WORD tests no case
    pinned. `fmt-kind-first` was labelled equivalent and is only unreachable; `snext-function` was credited a kill its
    full run never finishes. The registered rows were not each routine's worst (fs_back 1.03 at 60 characters against
    1.077 at 250; the with-thunks headlines each ~0.01 low).
  - fs_input (R3). Three order holes shown by surviving mutants: the read block's order (a row put down against OK put
    down), `top := 0` by a read pinned only when the read had a pass to itself, and the survivor `row-folder-is-file`,
    called EQUIVALENT, killed by real data — a NEW ROM FINDING (a spec past ~25 characters overruns the title into
    the first row's kind byte: the row is taken for a folder). Memory between the last wait and the end was held by
    nothing but the VDI arguments. The spin refusal's comment claimed no other path reaches it; one does.
  - COST (R4). `make test` quiet went **140 s → 397 s**: xdist's `load` handed one worker the whole of
    `test_aes_fs_input.py` (391 s of the 397); each session was derived 5 times where 2 are needed and its C run in
    two children; the sweeps and Tier 3 redid a whole session once per slice row; registry import +15.7 CPU-s per
    process and 2.1–2.35 GB peak RSS per worker (the 16 MB image kept per GEMDOS call); `make bench` +56 % CPU. Three
    generations of recording trap handler; `RUN_INSNS` a second budget mechanism; `aes_fs_input` 87 lines, five deep.
  THE FIXES.
  - FP (performance and mechanism; no bench row moved, the table byte-identical before and after its levers; all 1,574
    rows + 29 slices hash identical under the old and the new `merge_pokes`):
    - `--dist worksteal` in the PROJECT Makefile's `PYTEST_ARGS` (no kit change) and `test/conftest.py`, which collects
      the cases of one session back to back so a steal does not split them (the second session test: 163.6 s summed
      when spread → 33.9 s);
    - one derivation per case and one child per session (deliveries per session per process 5 → 2; the digest read
      off the session's own child); the sweeps once per session (`test_boot_snapshot` 195.2 → 97.7 s summed);
      `tier3.Sessions`, one pair of runs for all of a session's slice rows and companions (35.8 → 8.1 s, 26.0 → 4.3 s);
    - `case.merge_pokes` run-wise (import 26.7 → 20.9 CPU-s); `GemdosCalls` keeps the low 1 MB only (peak RSS at import
      2,348 → 510 MB; the bench process 2,500 → 1,278 MB);
    - `make test`, quiet: **140 s (HEAD) → 397 s (the wave) → 193.03 s** (load 2.6) and 194.64 s (load 8.2), CPU-bound
      on ten workers (1,476 s summed, with 111 more tests than R4 measured). The slowest test protocol 75.7 → 37.5 s.
    - THE PARTITION TEST (`tier3.uncovered_stretches`), RED-proved: on the table without the put-away it fails by name
      on two sessions (0.8784 and 0.8767 against a worst registered 0.8389). One test per sliced session, 3–13 s each.
    - The budget NEED-BASED (`_vet_not_stale` refuses 5N <= `DERIVATION_INSNS`; RED: fm_alert's 208,880 instructions
      under 1,500,001, which every size rule passed) and `run_event`'s one number split into `budget=` and `cap=`;
      `stopped_at`'s budget pinned as the cap (R1's survivor killed); `RUN_MARGIN` gone, `RUN_INSNS` a declared budget
      held to the margin by name; ONE ledger machinery, `aes_shell.Table`, under the scripted trap and the replay.
  - FT (tests, rows, C conventions):
    - PINS: a read-only (`$11`) and an archived (`$30`) folder on a disk of their own; `A:\BIG\F?0?.DAT` (101 read, eleven
      kept, no bell) with its replay twin; arrow `$0108`, row `$0100`; five sessions (80 now) for the read block's
      order, `top := 0` in the pass that reads, and the long spec's first row — each of R2's and R3's mutants killed.
    - WHAT THE SELECTOR HOLDS at every VDI call hashed into the ledger on both shores (`held_in`): R3's
      `SELECTED | 0x40` mutant, which neither suggested surface could see (inf_what clears OK's whole state word
      before the first free), is KILLED.
    - THE SPIN'S SECOND ROAD, derived from a ROM run and pinned (R3's mechanism was misread: under the path lie the
      AES's four text buffers, not a linked table): the ROM's own ob_draw of a formatted text whose template runs 77
      characters, then `\*.*` and the close box.
    - WORST ROWS re-registered from `make bench`: the put-away as its own slice in every priced session (0.88), the
      Return and Cancel rows split at fm_do's last unsync, fs_back and fs_pspec at 79 characters (1.04 / 0.96),
      fs_active's hundred 8.3 names (0.83, 0.94 with thunks), fs_nscroll eight rows down (0.80), fs_newdir thirty-four
      names (0.82), two more priced sessions (a root with no drive; a spec that fills the title's scratch).
    - `aes_fs_input` split into `struct selector_run` + five helpers (the entry 19 lines; 258 bytes shorter; 18 of its
      rows moved by -102..+40 cycles, no printed ratio); the glue's park / trap / verdict in one helper per frame shape
      (the target `gemdosif.o` byte-identical); the duplicated constants onto the existing ones.
    - THE CLOSE BOX'S ARM, 1.20 → 0.96. Cut alone from fm_do's end (R1's own argument for the put-away), the close box
      over a root with no drive measured **1.2043 own / 1.2506 with thunks** — over the bar — behind a wait-cut row of
      1.03: GCC had INLINED fs_back's downward scan into fs_input at both of the close box's sites, reloading the
      image pointer every byte (94 and 114 cycles a byte against the ROM's 64), and only the ROM's 849-byte defect scan
      runs it long. The ROM CALLS fs_back there (`$fe815e`, `$fe818a`, Line-F), so the C now does (`fs_back_called`,
      noinline, 78 cycles a byte): the arm alone **0.96 own (0.9553) / 1.00 with thunks**, registered; the wait-cut row
      0.85 / 0.90. 19 fs_input rows moved, no other printed ratio.
  MUTATION (strict: a private `.so` or overlay per mutant, xdist, no `-x`; FT's with a CONTROL every fifteen), as
  finally reported:
  - fslib.c's event-free half + fslib.h + the glue: S1 claimed 223 / 8 / 0 of 231 (first pass 211 / 18 / 1). FT's
    final 239: **231 KILLED / 8 SURVIVED / 0 ABNORMAL** — four equivalent, two equivalent on every reachable machine
    (`fmt-kind-first` relabelled), two unobservable. `snext-function` is KILLED on its targeted run and ABNORMAL in its
    full run (the host's Fsfirst spins over real GEMDOS), not repeated.
  - fs_input: S2 claimed 205 / 8 / 0 of 213 (first pass, stopped at 106, 89 / 14 / 3). FT's final 224: **217 / 7 /
    0** — five equivalent, one equivalent on every staged machine, one unreachable; `row-folder-is-file` KILLED.
  - K (`aes_event.py`, `tier3.py`): 70 — **63 KILLED / 2 SURVIVED / 5 ABNORMAL** (first pass 57 / 8 / 5); the five
    are refused by name at import (a collection error, not a strict kill) and R1 showed each KILLED once armed after
    collection. Survivors: s19 equivalent; b21 unpinned then, pinned since by S2's blocking session.
  - FP (S2's `aes_event.py` additions + its own changes): 57 — **54 KILLED / 2 SURVIVED / 1 ABNORMAL**: a badly chosen
    mutant (it weakens a passing test's own assertion), one equivalent on every caller, and one refused by name at
    import. All five over S2's `declare_child_doors` / `stopped_at` KILLED.
  THE GATE (four finders over the fix pass: no candidate against the shipped C, no stale or order-dependent memo; 18
  items of test honesty, budget doors, memory, duplication and conventions) AND ITS FIX, which supersedes the lines
  above where it says so:
  - TEST HONESTY. One test failed ALONE (`test_a_routine_s_child_doors_are_declared_once`: the registry filled by
    another module's import) — fixed, and every test FUNCTION of the wave's 14 test files run alone, one id each in a
    fresh process: **515 run, 0 red**. Two REDs passed for another reason than they stated and one asserted nothing of
    its name's claim; a GREEN half had no case. Now: the cap's and the frames' budget's refusals are matched in their
    own words; a watched prefix's margin is asserted; fm_do's 38-key session with its keys in the ring (728,664
    instructions in ONE oracle run) is the in-process door case that declares one `budget=` for both its runs;
    `aes_shell.Table` refuses in words a pointer outside it or BETWEEN two entries (`next` too); `ram_in` refuses a
    memory of another length in its own words; the snapshot's three sweeps hold the premise they skip a session's
    other rows on (one machine), by name.
  - ONE BUDGET DOOR. `aes_event.capped_run` is where every in-process differential of the door's batteries is capped
    and vetted: `run_event`, `aes_fslib.run` / `run_replayed` / `run_session`, `test_aes_wm_update.run`. A raw
    `max_insns` is refused by name; a case's own cap is held both ways whichever battery it comes through (it was
    held only when it EQUALLED `RUN_INSNS`); a battery's is `aes_event.battery_cap(insns, deepest=)` — `RUN_INSNS` is
    now `aes_fslib.RUN_CAP`, and test_aes_wm_update's `CASE_INSNS` at a margin of 2 is `CASE_CAP`, re-declared from
    its measured 244,097 at the one margin (1,220,485). `held_to_the_margin` is gone. No verified content moved.
  - DISTRIBUTION AND ORDER. `--dist worksteal` is set by `test/conftest.py` for any xdist run that names no `--dist`
    (it was in the project Makefile's `PYTEST_ARGS`, which every documented override dropped), pinned on real runs;
    the collection order is declared by each battery with the marker `collected_with` — the selector's sessions, its
    priced sessions' cases, and Tier 3's sliced sessions (rows, companions and partition back to back) —
    `test/test_conftest.py`.
  - MEMORY, measured (`/usr/bin/time -l`, one serial process, before → after): the partition test of the selector's
    longest session alone **1,924 → 946 MB**; `test_tier3.py` **3,781 → 963 MB**; `test_boot_snapshot.py` **1,071 →
    730 MB**. A watch was a reference cycle (its own bound methods handed to itself), so a session's marks outlived
    its pricing until a later collection; a kept refusal's traceback held them too. ONE memo class
    (`aes_event.OncePerSession`, built with its computation; `tier3.Sessions(bench)` is one build's) keeps sliced
    sessions alone, the companions' memo keeps four small fields and not two images, the io sweep keeps nothing; a
    pass's memory is its megabyte of RAM; `_trapped` no longer copies sixteen megabytes per GEMDOS re-enactment. A
    test with the collector OFF holds the marks' release.
  - SCAFFOLDING AND DUPLICATION. K's pre-C rig of fs_input (a third staging of its machine, raw object numbers, "no C
    fs_input exists yet") is gone: the mechanism's tests — the eight-shape partition, every RED — run over
    `aes_fslib.fs_input_machine` (the TEN folder; 631,480 ROM instructions, the shapes re-measured) through the public
    `rom_sliced` / `rom_timeline` / `slice_cost`; the private twins are removed. A Tier 3 row carries its registered
    name (`Row.registered`, `tier3.session_of(row)` — a sliced row that names no session is refused), the nine
    re-spellings gone. One `string_in`, one set of selector spans, one `folder` / ROOT_PATH, one UNREAD_BYTE and one
    astray-run helper, one VDI_TRAP; the unused parameters and `DOTTED_DISK` removed; the child's GEMDOS refusal
    (`CHILD_GEMDOS_REFUSED`) reached by a test. A session cut at two trap handlers one of which nests in the other is
    refused by name where it happens (RED on the watch; no session does).
  - CONVENTIONS. The drag distances, the frame offsets (`aes_fslib.active_arguments` / `newdir_arguments`, …) and the
    priced sessions' wait ordinals are named; `SLICE_INSNS` is `DIFFERENTIAL_INSNS`. `read_directory`'s four levels
    are two (`marked_entry_is_listed`, the same statements in the same order): the target `fslib.o` is the ONLY object
    that differs from the pre-fix build (106 of 107 byte-identical), and **15 rows moved** — fs_active's 6, fs_newdir's
    4, fs_input's 5 that read a directory — by +1..+201 instructions and -378..+6 cycles on ours; no ROM column, no
    printed ratio and no verdict moved, none added or removed.
  - MUTATION of the gate fix (strict; Python mutants as private copies loaded in place of the module, in the children
    too; three CONTROLS, all SURVIVED): 53 over `aes_event.py`, `tier3.py`, `conftest.py`, `aes_shell.Table`,
    `aes_fslib.py` and the batteries' group declarations — **51 KILLED / 0 SURVIVED / 2 ABNORMAL** (both refused by
    name at import: a sliced row whose registered name is its label; a watch whose `opened` is not kept — collection
    errors, not strict kills). Over the restructured `read_directory` and FS_EMPTY_ROW: **10 / 10 KILLED**.
  COVERAGE (llvm-cov, -O0, after the split and `fs_back_called`; 492 tests): `fslib.c` **99.27 % of lines** (3 of 410
  missed), **98.51 % of branches** (2 of 134) — the host refusal's taken arm (it runs in a child that aborts: no
  profile) and `act_on_the_object`'s dead upper bound. S1's own build had the event-free half at 100 % (58 branches).
* **Wave 13 band 4 wave 0 (2026-10-04) — the door made rebindable and tak_flag rebound; gemasync's lists; the PDs and
  the pipes.** A read-only scoping of the band first (81 routines / 7,074 B, 74 to port; the switch measured; every
  (EV) row re-priced in prediction — the section intro has it), the orchestrator's rulings Q1–Q7 on its open questions
  (the section intro), then three agents in one tree with disjoint owners — F (the rebinding protocol and the tak_flag
  pilot), A (gemasync's lists), P (PDs and pipes) — four reviewers (R1 slice F; R2 slice A; R3 slice P; R4
  cross-cutting: cost, seams, shared headers, the table, conventions, bands, children, claims), a fix list, and two fix
  agents in parallel (XA the protocol, the lock, the lists and the seams; XP the processes and pipes). Result: 18 ✅
  routines, 55 new Tier 3 rows (50 C, 5 `.S`), every one within the bar or `transcribed`; 88 committed rows moved by
  FLIP 1 and no other. The kit is untouched (ruling Q7).
  - F (THE PROTOCOL, `include/aes/evdoor.h`, `src/aes/evdoor.c`, `include/aes/switch.h`, `test/aes_event.py`,
    `bench/tier3.py`; the pilot `src/aes/evsync.c`):
    - THE THIRD ANSWER. `recreate_call_event_door` answers REFUSED / SERVED (the nested ROM run, as before) / ARRIVED
      ("noted: run the twin"). A rebound entry's wrapper packs its frame and asks as before; the case records the frame
      for the frames-handed comparison and lays the interrupt due at that call; the twin runs; its answer is reported
      to a second hook, `recreate_event_door_returned`. On target the wrapper is `return aes_<twin>(image, …)` and
      nothing else. A wrapper and a hook that disagree halt by name, both ways.
    - `REBOUND` IS DERIVED — the entries whose core the candidate library exports (`aes_event.rebound_in`), and at
      Tier 3 the blob's symbols (`tier3.twin_entries`), held equal; an entry that has a twin AND a `jsr` into the ROM
      is refused by name.
    - THE SHADOW (`aes_event.SHADOWED`, the flip in flight): the ROM routine's nested run over a COPY of the image at
      the arrival, the twin's answer and image held to it at its return. It names where a red is — at the twin's own
      call, not 400,000 instructions later at a session's end.
    - THE REFUSING DISPATCH HOOK (`recreate_dispatch`, ruling Q1): a twin that reaches dsptch asks it before any
      guard, and it refuses by name, a block told from a yield by PD_STAT as disp tells them. WHAT IS COMPARED TODAY:
      the hook and the halt store nothing — the child's image is the image it was handed, the ROM's at dsptch. No C
      runs between an entry and dsptch yet, so NO C IS HELD TO THE ROM AT dsptch BY THIS WAVE; the mechanism that will
      hold one (a blocked rebound entry compared where its twin stops) is pinned on the ROM's side, and THE COMPOSED
      PATH FIRST RUNS IN WAVE 1.
    - TIER 3's ARRIVALS RULE: both runs still arrive at a rebound entry — ordinal, delivery, slice mark, frame held
      equal — and it opens a window of NOTHING: the ROM routine's cycles stay the ROM's own, the twin's are ours. A
      twin that runs any AES ROM cycle is refused by name. Mixed rows (one rebound call, one ROM-served) work because
      windows are per call; the table's sub-line counts "N call(s) of a rebound entry in the own cycles".
    - THE SR SAVE WORDS: ONE named drop exists, psetup's (`aes_event.SR_PSETUP_DROP`). The dispatcher's and
      spl7_save's are named when a case first reaches their bracket — none does in this wave.
    - FOUR RED PROOFS: a mutated twin reds in the shadow at its call (four real C mutants, each killed by the shadow's
      own words over door cases of OTHER routines); an entry left ROM-served while its twin exists reds the derived
      test (a scratch blob with the target wrapper left on `jsr`); a delivery laid one arrival late reds on a rebound
      entry (the ordinal — a delivery tak_flag neither reads nor writes commutes with it, measured over all 56
      interrupted rows: 442 addresses written, none in the semaphore or rlr); dsptch reached is refused by name.
  - FLIP 1 = tak_flag (`$fe4e5a`): count up; the owner is rlr or the count is 1 → the owner stored, 1; else the count
    put back, 0. Its own battery: every lock state the scheduler's own, the lock with a process queued on it included.
    - THE TABLE: 1,689 → 1,743 rows before the fix pass — none removed, 54 added, **88 MOVED, no other row moved**
      (three parsers agree: F's, R1's raw diff, R4's). Every moved row keeps the original's column; ours changed.
    - WHY: the ROM's tak_flag — its body and its Line-F return — is **364 / 384 / 376 cycles** a call (the caller's
      own / free / refused), exactly the old window sizes, now in the ROM's own column; the twin is **226 / 214**
      (free / the caller's own). 80 of the 88 carry "call(s) of a rebound entry" (1–5 calls). The other 8 moved by
      the wrapper's change of SHAPE: wm_update's two releases and "2: the screen given back" (`aes_wm_update` compiles
      30 / 28 cycles smaller now that tak_flag is an ordinary call and not an inline `jsr` with D2/A2 given up), and
      five fs_input slices (-30: a wm_update(0) inside; +8 ×4: a slice ending at the lock's arrival is marked at the
      twin's first instruction, the call's pushes before the mark).
    - HOW FAR: 20 rows moved at two decimals — wm_update's six (0.43 → 0.48 ×2, 0.43 → 0.36 ×2, 0.34 → 0.36, 0.34 →
      0.33), fm_own's three (0.34 → 0.38 ×2, 0.28 → 0.38), wm_set's four (0.20 → 0.27, 0.22 → 0.28, 0.21 → 0.28, 0.36
      → 0.39), gr_dragbox's four (0.78 → 0.77), gr_slidebox's three (0.71 → 0.70 ×2, 0.75 → 0.74). Largest +0.10 and
      -0.07. **The highest moved row is 0.82; nothing is within 0.03 of the bar that was not before; NO VERDICT
      CHANGED** (all still `net`). Against the prediction: wm_update 6 as predicted; fm_own 3 of 4 (its give-back
      takes no lock); every row that takes the lock through them, by one tak_flag window (~380 predicted).
    - R1 re-derived five moved rows instruction by instruction from the two blobs' listings: both columns close, in
      a mixed row too. GCC now inlines wm_opcl into wm_close, so `aes_wm_close` calls `aes_rc_copy` itself (one pair
      added to `transcription.C_CALLERS_OF_TRANSCRIBED_CORES`); `wmupdate.c` is the only pre-existing object of 126
      that differs. Every sliced session's partition test is green.
  - A (`src/aes/evasync.c`): signal, azombie, get_evb, evinsert, takeoff, apret, acancel and geminput's evremove — C
    at 0.48–0.83, no acceptance, no `.S`. Their machines are ARRIVALS: the ROM's own run of a scenario (the
    dispatcher's loop taking a key, a press, a mouse move, ticks; an evnt_multi parked and woken; a message; the lock
    handed over) watched at the eight entries (`aes_event.EntryStops`), each call verified from the machine and the
    frame the ROM makes it with — 187 calls in 20 scenarios, direct and through Line-F; two scenarios over the staged
    application (two delays pending), Tier 1 only. Arms no caller reaches (apret's 100 / 101 and its non-last unlink,
    acancel's filter, signal's evwait test) are pinned by arguments handed directly over ROM-made machines, each
    labelled. All 167 unlabelled arrivals were priced before registering; each routine's worst is its first row.
  - P (`src/aes/pdpipe.c`, `pdpipe.S`): pd_match, fpdnm, getpd, pstart, doq, aqueue, ap_find in C at 0.19–0.98;
    gemdosif's uda_insuper and psetup measured over the bar in C (1.50, 1.24: the image pointer's floor on a tiny
    hand-68000 body) and ship byte-pinned as `src/aes/pdpipe.S` (1.00; region `$fe3970..$fe39a5`, two
    `include/transcribed.h` rows) — the design had put psetup's words in wave 2's `switch.S`; the bench gate could
    not go green without them now. psetup's SR dance is `aes/switch.h`'s pair over `$8998`; its `.S` rows drop
    nothing, the one place the word is compared.
    - THE STAGED APPLICATION (ruling Q2, `test/aes_pdpipe.py`): the ROM's own pstart over a stub of exactly three
      instructions — a push of one immediate, ONE Line-F call of an allow-list (`ALLOWED_CALLS`: ev_mesag, ev_timer,
      wm_update, each with its reason), `jmp (SENTINEL).w` — vetted where it is made AND as it lies in the machine
      where it is entered; `called` is the dispatcher's own run carried on until the application's call parks it.
      Used for: fpdnm / ap_find's third PD, psetup's second frame, two waiters on one list, a third process's
      reader, the lists' two pending delays. No row of any registry runs over one (`case.ROW_REGISTRIES`,
      `transcription.TRANSCRIPTIONS`: held by a test with a companion that registers three and sees all three).
  THE REVIEWS. Verdict: THE SHIPPED C IS FAITHFUL TO THE ROM — R1, R2 and R3 read all 18 routines instruction by
  instruction — BUT FOR ONE BOUNDARY: ap_find's named refusal fired ONE CHARACTER EARLY (R3). Every other finding was
  test honesty, dead code, a helper that was not what its docstring said, wording a measurement contradicts, or cost.
  - THE RULE (R1): **A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION.** 22 real C
    mutants of `aes_tak_flag` against the door batteries of seven routines (1,126 tests): five that are not
    equivalent pass every one — the refusal with a real other owner, the owner's and the pointer's widths, the wait
    list — shadow ON OR OFF, because a door case reaches an entry only in the states its caller makes and the shadow
    sees the same states. `test_aes_evsync.py` alone kills all five. The shadow changes where a red is NAMED, never
    what is covered: "the shadow / the door cases cover it" is no coverage argument for a flip.
  - R1, the rest: the three SR save-word drops were dead code and `switch.h` said they were in use; a RED matched
    any dead child (its `match=` was the head of every refusal); RED proof 4 compares nothing a C wrote (above);
    tak_flag was never handed the one real state whose wait list is not empty; a twin that called another entry's
    WRAPPER would shift every later ordinal on the host alone (the hook counts every wrapper call, both watches the
    outermost) — unreachable for a leaf, a trap for wave 1. The arrivals rule's accounting: CLEAN, to the cycle.
  - R2 (the lists): apret's unlink from its process's list never stored a non-zero link (a surviving mutant; no ROM
    call can show it — ev_multi's aprets take the deepest EVB first); evremove's comment claimed a delay's ticks could
    be taken for a click count (tchange clears the parameter first); the child-first guard's cost and its proposed
    lever both mis-stated (205 children, not ~250; the reduced guard LOSES a kill); "every read is where the ROM
    makes it" pinned for one alias only; the `$c84e` finding incomplete (three writers unread).
  - R3 (the pipes): ap_find's boundary (the ROM serves eleven characters — measured through its own trap door);
    five survivors called "equivalent" killable on machines the ROM itself makes (its own pipe overrun taken 96
    bytes further rewrites PD1's queue pointer and the spare PD's status); no 68000-semantics or re-read mutant in
    the sweep, eight surviving; `called()` re-entered the stub from the harness instead of carrying the dispatcher's
    run on; three holes in the staged application's guards; the attribution opt-out per ROUTINE hid five aqueue
    cases that pass poisoned; "the ROM's run never returns" false for doq's own refusal case; an odd index walked
    past.
  - R4 (cross-cutting): the wave cost +4.3..7.1 s of suite wall; three things A and P asked F for were built and not
    adopted (each then existed twice); the child-first guard keyed by `id(machine)` (a freed dict's address is the
    next one's: RED-probed); the same helper spelt three and five times; `test_aes_evsync` not child-first. CLEAN:
    the table, the pre-existing objects, the staging bands, the host slots, the children, the rows' hashes.
  THE FIX PASS (where it contradicts an author's report or a proposal, the fix report and the final table stand).
  - XP — ap_find SERVES ELEVEN, the one behaviour change: the slot is the frame plus the saved A6's two top bytes,
    the refusal on the twelfth byte; one byte of the target object differs (a displacement, 1,408 B both); its two
    rows did not move. The ROM's side is pinned IN the battery through its own trap door. R3's five "equivalents"
    and eight semantics mutants all KILLED, the "unreachable" count re-read too (a queue pointer the ROM's overrun
    moved to just below the QPB), on machines nothing is poked into. `called` is ONE watched run of the dispatcher's
    loop. The staged application vetted where entered, against pstart's own ledger, by an allow-list. The opt-out
    per CASE with a named reason (69 ids steered, 125 poisoned, measured each alone). doq's refusal KEPT for every
    count with its reason corrected (`## Not reconstructed`); the odd index pinned on three shores; doq's worst row
    re-registered from 23 candidates (+1 row, **0.98**, was 0.97). `offset_by`, `FRAME_LOCAL_WORDS` and
    `onto_the_woken_list` hoisted (the m68k objects of fmlib / obedit / shell_find / evasync byte-identical).
  - XA — the dead drops deleted (one `SR_PSETUP_DROP`); the loose RED matched on its reason, with a test that a child
    dead of anything else is not taken for it; the lock with a process queued pinned (SPB_WAIT left alone); THE RULE
    written into `aes_event`'s docstring and held by a derived test (`test_every_rebound_entry_has_a_leaf_battery_s_
    rows`); "a twin calls a core, never a wrapper" documented in `aes/evdoor.h` and held by the build
    (`test_no_twin_s_object_calls_a_door_wrapper`); apret's non-zero unlink pinned by a labelled case; the case over
    the lever's poked list DROPPED (the strict re-sweep without it kills the same 110 of 117); `AES_TIMER_LIST`
    renamed `AES_ZOMBIE_LIST`; `$c84e` re-derived from every reference in the GEM text (the first report's "never
    returns to 0" RETRACTED). ONE child-first guard, `aes_event.returns_in_a_child`, remembered by CONTENT; the
    FORK guard adopted on measurement for cores that reach no hook (the lists' battery serial 18.2 s with a fresh
    interpreter and a 16 MB image file per call → 12.2 s forked, 10.5 s with no guard; five whole-suite runs under
    xdist green; the three mutants whose C does not return still FAILED cases). Public `as_pokes`, `EntryStops`,
    `dispatched`, `ticks`; one list walker. No shipped-C behaviour change: the m68k objects of `evasync.c`,
    `evsync.c`, `wmupdate.c`, `evdoor.c` byte-identical to the pre-fix tree's, all 1,651 row hashes identical but
    XP's 26, and NO table line moved by XA (the table gained XP's one doq row: 1,744).
  THE PRE-COMMIT GATE (gate 8: four finders over the fixed tree) found NO DEFECT IN THE SHIPPED C — sixteen routines
  re-read against the disassembly, all four build configurations linking, the blobs byte-identical — and eighteen
  items in the fork guard, the watches, the tests' honesty and the conventions. ITS FIX PASS (2026-10-04) changed
  no shipped behaviour: all 130 m68k objects, the bench and the shipped configuration both, are byte-identical to
  the pre-fix build's (one accessor for a record's signed word hoisted over three copies, getpd's accessory-table
  read put on the bus — a host-only difference —, `pdpipe.S`'s mark named); every one of the 1,652 rows' hashes is
  identical; no line of the table moved.
  - THE FORK GUARD IS MADE AT THE CALL. `aes_event.run_core_guarded` makes EVERY run of a hook-free core's C in a
    fork first — the plain pass's AND the attribution pass's, each over the image and the library state the kit
    hands that run (`aes.run_function`'s `first=`) — so the poisoned run is guarded and no verdict depends on the
    test before. The pipes' battery runs behind it like the lists' and the lock's; its 23 fresh-interpreter
    children are forks too (`core_in_a_fork`: the image read back through a shared mapping, the library armed
    first). `returns_in_a_child` is the door users' alone again (`door=` is gone), remembered by THE IMAGE the
    pokes make (two overlapping pokes laid in the other order are another machine: RED-probed, forked once before).
    In a fork: Python's `sys.stderr` is the pipe too (a hook's words were lost without `-s`); a fork whose own
    Python raised says so, traceback and all, under an exit status of its own (it shared 3 with a child's VDI
    refusal, and read "the C did not return"); EVERY hook the library exports is bound to a refuser that names it
    (a core reaching a `void` hook returned having skipped the effect: a vacuous green) — the list held to `nm -g`,
    and the fork-guarded cores held clear of them on any path by the host build's own call graph; the alarm is the
    fork's first act, which bounds an orphan (README: the check that sees one — the old `/ctypes/` check could not).
    XP's ABNORMAL mutant `sem-getpd-unsigned` — an abort in the attribution pass, in process — is a clean KILL.
  - THE ATTRIBUTION OPT-OUT IS ONE SPELLING, AND AN ASSERTION: `aes.run_function(steered=<reasons>)`, used by the
    pipes and the lists alike. A reason names THE WORDS that steer, and a steered case still makes the pass —
    NARROWED to them: every other byte the ROM's run stored inverted. So a wrong or incomplete label fails by name,
    and 467 case ids that ran with NO pass (393 of the lists', 74 of the pipes') now run all of it but those words;
    157 run the kit's whole pass (75, 69 and the lock's 13). The 17 mislabelled
    opt-outs are corrected (pstart: the PD count, then the stack — a new reason; the eight aqueue writes: the index,
    then the lists), two overlap reasons added (a queue pointer, a QPB the run's own copy lands on), and the sweep
    that asks whether each reason is NEEDED (`AES_STEERED_FOR_NOTHING`, on demand) found six named for nothing —
    three aprets that refuse, two doq overlaps, aqueue's one-byte write — which now run what they can.
  - THE WATCHES. `EntryStops` refuses by name a run that would END having executed nothing (an end that is its own
    entry: the "machine" handed on would be the staged one) and a gate that is itself an end, and never arms the PC
    it is stopped at — on which the KIT's watch loop spins for ever (deferred: `## Not reconstructed`); its
    docstring says when an entry is watched again, and what that cannot see. A twin's arrival is BOUNDED to our
    blob's own text. Tier 3 tells a rebound call from a served one by what the watch saw, not by a window of zero.
    REBOUND is read at the moment a run is made, one derivation. The shadows are a binding's own list, emptied when
    a case opens it, a call's place taken before its shadow is made. The settled SR word is derived through the
    vetted run, once per routine.
  - THE DERIVED TESTS. "A twin calls a core, never a wrapper" follows calls ACROSS FILES — the host build's own call
    graph, function by function (`test_no_twin_reaches_a_door_wrapper`, replacing the one-object `nm -u`), its
    compile taken from kit.mk as make expands it; the leaf-battery test says what it holds (that a battery exists).
  - THE STAGED APPLICATION is vetted on EVERY road that runs the dispatcher into its stub (the dispatcher run to its
    aqueue, and the lists' two-delays scenarios, were not), for its ARGUMENT and its width too — the width now the
    call's (`ALLOWED_CALLS`), not a caller's flag; a QPB that would land on the stub's room is refused where staged.
  - TEST HONESTY: psetup's "is all that is dropped" holds that ONLY `$8998` differs; each forged stub is refused by
    its own reason; the two cases over a poked field (a tagged owner, a tagged `rlr`) are LABELLED argument-class
    cases, the lock battery's docstring corrected; the lists' three cases over the staged application carry the
    label and a test holds that battery to it.
  - STRICT MUTATION of what the fix pass changed, 72 Python mutants of the guard, the watches, the vets and the
    steered pass: **69 KILLED / 3 SURVIVED**, each equivalent (the shadow's fast path skipped or laid wider falls to
    the address-by-address compare; an SR word asked of every row is the same rows). The entry-left-armed mutant —
    "not swept, by nature" before: it spun for ever — is a clean kill. THE WAVE'S 328 C MUTANTS RE-SWEPT under the
    new guard and the narrowed pass, no test weakened: the pipes' 156 — **141 KILLED / 12 / 0 ABNORMAL** (+3 refused
    by the compiler; `sem-getpd-unsigned` killed), the lists' 129 — **115 / 14** (`e12-pending-unsigned`, reported
    EQUIVALENT, is KILLED by the narrowed pass: the pending count inverted is negative, and evremove's compare is
    signed), the twin's 43 — 40 / 3, as before. These supersede the totals below.
  - Corrected counts: test_aes_evsync is 10 functions / 13 cases (F reported "10 / 12" over 9 / 12); tak_flag has no
    REGISTERED Line-F row (F's proposed "+ 2 Line-F" are two Tier 1 cases); F's "every in-process case of mine runs
    its child first" was not true of test_aes_evsync until the fix pass.
  MUTATION (strict: a private `.so` or module per mutant, never while editing), as the first fix pass reported it —
  the gate's fix pass re-swept every C list (above: 141 / 12 / 0, 115 / 14, 40 / 3):
  - XA, the lists' C (`evasync.c` + `evasync.h` + the two `aes.h` fields; A's 117 + R2's 12): **129 — 114 KILLED /
    15 SURVIVED / 0 ABNORMAL**. A's seven as before (4 equivalent, 1 equivalent on every reachable machine, 2
    unreachable: get_evb's empty list, NOCANCEL alone); of R2's twelve, 4 killed, 4 survive ALIAS-ONLY (the unpinned
    re-reads), 4 are no-ops by construction.
  - XA, the twin and the protocol's C (`evsync.c`, `evdoor.h`'s host protocol, `switch.h`'s dispatcher entry; F's 35
    + R1's 8): **43 — 40 / 3 / 0**: rlr read once for the store and the owner stored only when free (both
    equivalent), a transient scribble of the count put back inside the call (unobservable at any return).
  - XA, the Python machinery (`aes_event.py`, `tier3.py`, `aes_evasync.py`; F's 43 + 34 of the fixes'): **77 — 75 /
    2 / 0**, three controls green; the two are the shadow's one-compare pass (equivalent: each falls through to the
    address-by-address compare with the same verdict). One mutant NOT SWEPT by nature: a watch left armed at its own
    stop never ends.
  - XP, `pdpipe.c` + its constants (P's 128 reworked + 28 new): **156 — 140 KILLED / 12 SURVIVED / 1 ABNORMAL**, 3
    more refused by the compiler (static asserts). The twelve: 4 equivalent, 4 the accessories' arm (band 5), 3 a
    re-read no store reaches on any machine made, 1 the room wider than a word (`## Not reconstructed`). The
    abnormal one differs only for a count the attribution pass's inverted word reaches — it aborts there, no failed
    assertion. `pdpipe.S` is not swept (byte pin + 5 `.S` rows + `test_transcribed`).
  - Authors' own first sweeps, superseded: F C 35 — 34 / 1 / 0, Python 43 — 42 / 0 / 1; A 117 — 110 / 7 / 0; P 128 —
    114 / 13 / 0.
  COVERAGE (llvm-cov, -O0, the authors' builds BEFORE the fix pass, not re-run after it): `evasync.c` 100 % of lines
  and regions, one branch of 44 one-sided (get_evb's empty list); `pdpipe.c` 91.95 % of lines, 84.09 % of branches
  (the accessory arms and the three refusals, which run in children that abort without a profile). No coverage claim
  is made for `evsync.c`: its three arms are each pinned by killed mutants.
  SUITE TIME, quiet, pytest's own figure under `-n auto`: HEAD **193–197 s** (193.1 and 195.8 in the fix pass's A/B,
  195.8 and 197.2 in R4's); the wave before its fixes 201–203 s; the tree after them **196.8–202.4 s over seven runs,
  mean 200.0** (three with a five-minute cool-down: 202.43 / 199.72 / 199.12). THE 200 s LINE IS NOT HELD WITH
  MARGIN: the wave sits AT it, about +5 s over HEAD, run to run ±3 s. The fixes took the wave's CPU overhead from
  +59..67 CPU-s to about +20 (the shadow's one-compare pass, the fork guard, no image read back by a guard's child,
  the image compared by blocks); what is left is 877 more tests. Nothing was weakened to get closer.
* **Next** — BAND 4 IS OPEN: the door is rebindable, one of its eight entries is rebound (tak_flag), and the lists,
  the PDs and the pipes under the other seven are ✅. Next is **band 4 wave 1 = I ∥ S**, which makes FLIP 2 — six
  entries, one commit (ruling Q6):
  - **I — input**: the posts (post_keybd, post_button, post_mouse, with nq, downorup, inorout, mowner, set_mown,
    ct_chgown), the four fork functions (kchange, bchange, mchange, tchange), forkq / forker (with the ONE
    `staged_call.h` fork hook, ruling Q3) / chkkbd, and b_click / b_delay. Flips post_button and ct_chgown.
  - **S — waits**: iasync and its arms (akbin, adelay, abutton, amouse, amutex; aqueue is ✅), mwait, unsync, ev_block,
    ev_button, ap_rdwr, and the small ev_* (ev_rets, ev_mchk, ev_keybd, ev_mouse, ev_mesag, ev_timer, ev_dclick).
    Flips unsync, ev_block, ap_rdwr and ev_button. Every blocking arm ends at the refusing dispatch hook, compared
    with the ROM at dsptch.
  - PREREQUISITES the review named, to land before or with the flip:
    - dsptch's 20 bytes brought forward as `.S` (its `jmp` to the ROM's disp), so the TARGET LINKS: `aes/switch.h`
      declares `aes_dsptch` on target and nothing defines it until wave 2's switch — unsync's and ev_block's twins
      call it;
    - THE SHADOW OF A BLOCKING ENTRY stopped and vetted AT dsptch: today's shadow is the nested run, which refuses a
      run that reaches the dispatcher, so a shadowed blocking twin would be refused at its arrival and never reach
      the dispatch hook;
    - A COMPLETE LEAF BATTERY PER ENTRY BEFORE ITS FLIP — its own rows, entered at the entry itself, reaching every
      arm (THE RULE; `test_every_rebound_entry_has_a_leaf_battery_s_rows` refuses a flip without them);
    - TWINS CALL CORES, NOT WRAPPERS (C amutex calls `aes_tak_flag`, never `evdoor_tak_flag`);
    - "laid one arrival late" shown ON THE IMAGE for the entries that read the fork queue (for tak_flag a late
      delivery commutes; for unsync / ev_block it will not);
    - RED proof 4's composed path — a twin running into the refusing hook, held to the ROM at dsptch — run for the
      first time.
  - **WAVE-1 PREREQUISITES from the pre-commit gate** (gate 8: each proved by a probe on this tree, none built in
    wave 0). Wave 1's FOUNDATION STEP builds them ONCE, before the six flips, rather than six times inside them:
    - A WATCHED RUN ENTERED AT A DOOR ENTRY. A watch stops at its run's own entry and refuses it ("not a door
      call"): today no such run is watched, but the first twin that calls another twin's core puts the twin's own
      leaf rows under the watch (ap_rdwr → ev_block, ev_button → ev_block). `DoorStops` takes the entry its run is
      entered at as a property, and `rom_at_dsptch` becomes public beside `dispatched`.
    - THE SHADOW KEYED ON HOW THE NESTED RUN ENDS — returned (answer, writes), or blocked / yielded (its image at
      dsptch, vetted at the dispatcher's hook) — and `SHADOWED` DERIVED, not hand-edited per flip.
    - ONE `ENTRY_FRAMES` ROW PER ENTRY deciding its frame, its GCC-frame reader AND ITS ANSWER KIND (post_button
      is `void`: the shadow compares a word no such entry answers), with ONE wrapper macro pair `EVDOOR_REBOUND` /
      `EVDOOR_REBOUND_VOID` in place of six copies of tak_flag's host and target bodies.
    - `EVDOOR_TWIN` (`noipa`) ON EVERY TWIN: GCC inlines a twin into a same-file caller (measured on evsync.c), which
      silently unwatches its arrival — its first instruction is no longer reached.
    - `aes_dsptch`'s `.S` BROUGHT FORWARD with its kind in the build contract (the transcription table has no kind
      for a `.S` entry that is no twin of a C core), and `__ASSEMBLER__` guards in `aes/switch.h` / `aes/evsync.h`.
    - A `{save word: reason}` SR-DROP TABLE in `aes_event` in place of `aes_pdpipe.REACH_PSETUP` (a drop chosen by
      routine name): the dispatcher's and spl7_save's save words get theirs there.
    - A RUNTIME GUARD REFUSING A NESTED ARRIVAL at the hook, by name (a wrapper called inside a twin's call).
  - Then **wave 2 = M ∥ D**: ev_multi and FLIP 3 alone (104 of the 152 (EV) rows and every sliced session re-priced,
    the partition re-run on each), beside the dispatcher — `switch.S` (the byte-exact routines and disp as asm under
    the new transcription kind, ruling Q4), the irq glue, disp's host core, idle, disp_act, mwait_act, the dispatch
    hook's real body behind a per-case switch. Then **wave 3**: the rows that SWITCH (every blocking entry
    blocked-then-woken, the yields, ap_tplay / ap_trecd, the two-process rows), and the door's retirement — the
    nested run, the hop checks, mechanism (EV) and its tests deleted.
  - Still owed: the bindings `$fde2e8` / `$fde30e`'s D0; the E_CHG recovery behind GEMDOS's termination record; aes.register's
    settled mask made lazy (its import cost); the per-worker fork server for DOOR children (the fork guard adopted
    this wave serves only a core that reaches no hook); a pin for the longword store-above-RAM refusal; THE SUITE'S 200 s LINE,
    which this wave sits at and does not hold with margin (`## Not reconstructed`, band 4 wave 0: the replay lever
    still untaken, tak_flag still shadowed); the registry's import cost; the parked project-wide levers; promoting
    `ganneheim/dev` → `main` (the user's call).

## Suite

`make test`: **19,275 passed**, 2 skipped (one of them the `RUN_SLOW`-gated placement search), 0 failed.
- Re-summed by the AES band 4 wave 0 GATE-FIX PASS on 2026-10-05 from its own FORCED rebuild (`rm build/*.so` first,
  00:20, load 3.2 at its start), `test/test_status.py` included and GREEN, run twice with the same count. That is +35
  over the docs pass's 19,240 (the gate's new tests of the fork guard, the watches, the vets and the steered pass) and
  +914 over band 3 wave 3's 18,361.
- WALL TIME, quiet, pytest's own figure under `-n auto`: **201.34 / 201.72 s** (loads 3.2 and 3.1 at their starts,
  each after a cool-down). The tree before the gate's fixes: 202.43 / 199.72 / 199.12 s, **196.8–202.4 s over seven
  runs, mean 200.0**; HEAD the same evening 193.1 / 195.8. So the gate's fixes cost about a second (every run of a
  hook-free core forked first, the steered cases' narrowed pass — 393 + 74 differentials that were not made before —
  against 23 fresh interpreters dropped), inside the run-to-run spread of ±3 s. THE 200 s LINE IS NOT HELD
  (`## Not reconstructed`, band 4 wave 0).
- `make bench` judges **1,744 rows**: 762 ok / 338 net / 284 through / 220 transcribed / 63 accepted / 31 glue / 24 own /
  13 pinned / 9 rule, none OVER or DRIFTED (rc 0 at the gate-fix pass, the table rewritten by its `make test` at
  00:22: IDENTICAL, line for line, to the table before the gate's fixes — and both blobs byte for byte).
- The AES has 920 of them: 338 net / 277 ok (the 92 `.S` rows included) / 189 through / 97 transcribed / 17 glue /
  2 accepted.
- Wave 0 added 55 rows (28 ok — 23 C and 5 `.S`; 25 through; 2 transcribed): tak_flag's 3, the lists' 21, the PDs' and
  pipes' 31. Against HEAD's table by row key: none removed, **88 MOVED — FLIP 1, every one a row that takes the lock
  or runs wm_update's re-compiled body — and no other**; 20 of them at two decimals, none over 0.82, no verdict
  changed (the wave log lists them). The (EV) rows' floor is 0.27 now (it was 0.20: wm_set's field with no arm).
- `make guarded`: **19,275 passed**, 2 skipped, 0 failed — the same as `make test` (the gate-fix pass's run, 00:36,
  201.99 s of pytest).
- `make -C atari -B all`: rc 0 (the gate-fix pass's run; every m68k object of `src/`, in the bench and the shipped
  configuration both — 260 files — byte-identical to the pre-fix build's).
- The kit did NOT change this wave (ruling Q7; `git status --short tools` is empty), so its suite and the other six
  projects' were not re-run: kit **1,192 passed** and Zynaps 4,751 passed / 4 skipped, BuggyBoy 296, Joust 4,368,
  Flying Shark 3,851, Bubble Ghost 1,909, Wonder Boy 6,465 are band 3 wave 2's numbers, carried.
- `names.txt`: 905 fn / 536 var / 449 cmt (+16 / +7 / +19, and acancel's `cmt` replaced; one `cmt` per address,
  checked over the whole file). `reapply.sh` was NOT run by the docs pass (it rewrites `decomp.c` and the Ghidra
  project): run it before the next naming pass.

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

**vdi — the BLITTER set of the Line-A rasterizers is DEFERRED (the user's call, 2026-09-26).** `$fc4dde` fills the ten drawing
vectors `$2A14..$2A38` from the blitter table `$fc4e0e` or the CPU table `$fc4e36` by bit 0 of its argument, and boot passes the
probe's 0/2 — so boot ALWAYS installs the CPU set and only XBIOS `Blitmode` on a machine with the chip can flip it. The blitter
bodies (`$fca20a`, `$fca5ca`, `$fcee66..$fcf963`, `$fcf9be`, `$fcfccc`, `$fd0674`; ~4.4 KB) start the chip with a `bset #7`
busy loop on `$FF8A3C` and let it move memory the kit does not model, so their RESULT is invisible to every surface; at best a
register-write ledger. They stay unreconstructed, with the four console blitter routines below, until the kit has a blitter model.

**vdi — PARKED after band 2: `clear_span`'s home, the two CODE entries a rebuilt ROM still owes, setres's switching arms, and the
bus idiom's older sites.** The BIOS's span clear (`$fc4b7c`) lives in `src/vdi/screen.c`/`.S` and is named `VDI_ROM_CLEAR_SPAN`,
though it is a BIOS routine (the name mislabels it): the `.S` mechanism — the `vdi_rom_`/`linea_rom_` roles, `target.mk`'s
`src/vdi/*.S` wildcard, the ROM-data census — is VDI-scoped. Moving it to `src/bios/clear_span.{c,S}` needs a `bios_rom_` role in
`TRANSCRIPTION_ROLES` and the naming rule, the wildcard widened (with `isr.S`/`trap.S` kept out of the `.globl` check) and the rename —
a harness change of its own, which would also undo the layering inversion of `pexec_load.c` including `vdi/screen.h`. A REBUILT ROM
owes etv_timer the LINKED `vdi_rom_timer_tick` (it exists now; nothing stores it, because the ROM build compiles no core yet) and
USER_TIM's default `VDI_ROM_NOP` (`$fca652`, the `rts` ending `$fca648`) a shipped `rts`, which does not exist yet — both are CODE
entries in `test_vdi_rom_data.py`. setres's two resolution-SWITCHING arms halt inside XBIOS `Setscreen`'s resolution arm
(`console_reinit`, `$fca914`, not reconstructed — see the console paragraph below; it `bsr`s into `$fc4a48`, the body of the escape's v_fontinit that band 4 transcribed); what they ask for and that they store nothing
first is pinned, what follows is not. And the base-0 `bus_dereference` idiom (`include/m68k_idioms.h`, masked on the host only) is
adopted by `text.c` alone: `mouse.c`'s `peek16`/`poke16` and sprite/packet sites, `blit.c`'s `bus()`, `fill.c`'s `queue_word` and its
colour read, `screen.c`'s `span_bytes`, `palette.c`'s `bus_read16`/`bus_write16` and `gemdos/dispatch.c`'s redirected write still
mask unconditionally (`bus_address`, or `OS_BUS_ADDR_MASK` directly) and pay the `andi.l` on target — a cost, not a divergence; the builds compute the same function.

**vdi / kit — PARKED at band 2's code-review gate (each its own change).** The kit's `machine.h` `be16`/`be32`/`wr16`/`wr32` are
pointer-cast accessors, a strict-aliasing (TBAA) hazard in EVERY project's target build — only tos102us passes `-fno-strict-aliasing`
(buggyboy, joust, zynaps, flyingshark, bubbleghost do not) — so the fix, a `may_alias` access type in the kit, ships with the PRG
goldens re-run. (T→G)'s deeper lever is generated INLINE frame pushers, so C calls a `.S` with no thunk to net off. The attribution
(poison) opt-out is whole-routine (`vdi.READS_A_POINTER_IT_WRITES`); a kit per-span exclusion would keep skipped-store detection for the
rest. setres's switching arms pin the MODE through the halt's stderr wording, and `test/vdi_screen.py`'s `WORD_CALLER` is hand-built
(generalise from `declare_alcyon`'s frame). The Pexec rows are (T→) now, through `clear_span`'s `.S`: the refused-mode arm reaches
none of it and its 1.79 pin measures the same 226 cycles on either blob (reason text says so). `span_bytes` masks BEFORE its bound, so
the loader lost unmasked-address detection, while the GEMDOS accessors assert unmasked; and `gemdos_assert_inside_ram`
(`include/gemdos/gemdos.h`) still spells its bound `at + width`, which wraps for an `at` near 2^32 — the sum `span_bytes` dropped.
`bcon.h`'s BIOS trap helpers take plain `d` inputs under clobbers that include D1/D2, so a second argument lands in a callee-saved
register (init_timer_mouse's Setexc vector sits in D4) — the class `xbios.h` fixed with register-bound operands. And the older VDI
files keep local `WORD_BYTES`/`LONG_BYTES` copies of `VDI_WORD_BYTES`/`VDI_LONG_BYTES` (`helpers.c`, `inquire.c`, `mouse.c`,
`palette.c`, `text_raster.c`).

**vdi — band 3's honest gaps and what its code-review gate PARKED (each its own change).** A DOCUMENTED DIVERGENCE: at a rotation
that is not a right angle, d_justified's gap steps are whatever vqt_extent left in the stack frame (the ROM reads its leftovers, the C
reads 0); through v_gtext's own entry the same frame words are pinned on the harness's zeroed band, through d_justified they are
not pinnable. UNPINNED: a gdp_rbox OUTLINE whose wrapped segments send clip_line (`$fcbf16`) into a CYCLE never returns in the ROM
(four measured geometries — HUGE at any width, (0,40,32767,160) at width 3, (−16384,40,16400,160), the flat (−20000,100,20000,100);
period 196), so the seven wrapped geometries that DO return are pinned and these are not; v_clsvwk's not-found walk has no end test
and wanders through address 0's vectors, but no dispatcher call reaches it, so it is not staged. init_wk's interior and fill-style
clamps are spelt out rather than calling `attributes.h`'s `vdi_within_or`: the ROM compares the HIGH bound first and GCC lays the
helper out differently (eight spellings tried), +2 to +4 cycles on every init_wk and v_opnwk row. The HOST SIGBUS CLASS: every raw
Line-A pointer accessor (`linea_pointer` / `contrl_word` / `answer_intout` in `vdi.h`) dereferences a caller's pointer unmasked on
the host, so a stray pointer (poison, a mutant) is a dead worker rather than a red; no pointer the real machine hands reaches it, and
the overlap cases that need it run under `vdi.READS_A_POINTER_IT_WRITES` — routing the layer through `bus_dereference` is the
layer-wide fix (band 4 did the accessors; the ~90 held raw sites left are in its paragraph below). PARKED at the gate: the boot-snapshot audits run unsharded (+2 s per band); the gtext italic alignment grid (90
cases) could be trimmed; a general host WATCHDOG instead of the per-case `host_returns` bound; a per-span poison exclusion
(`poison_except=`) instead of the whole-routine opt-out; the bench table is rebuilt on every test edit (its prerequisite is `test/`);
the `always_inline`/`noinline` codegen choices (`line_style_mask`, `draw_arc`, `place_and_draw`) are held only by the Tier 3 bar.

**vdi — band 4's honest gaps and what its code-review gate PARKED (each its own change).** THE HOST SIGBUS CLASS, NARROWED: band
4 routed `vdi.h`'s call and workstation accessors through the bus (sum, then mask) and vdi_wline's PTSIN reads through
`caller_word`, but about 90 sites still hold `image + linea_pointer(...)` raw — `inquire.c` (vq_extnd, vql/vqm/vqf/vqt_attributes,
vq_mouse), `escape.c`, `gtext.c`, `attributes.c`, `arcs.c`, `fill.c`, `gdp.c`, `lines.c` (polyline, arrow), `blit.c` and `helpers.c`;
vq_extnd still SIGBUSes over a dirty INTOUT/PTSOUT (through `trap #2` the PTSIN-held sites are always clean, PTSIN being the copy). A
PREMISE FOUND FALSE: `atari/target.mk`'s reason for `-fno-jump-tables` (absolute addresses in rodata) does not hold for
`m68k-elf-gcc`, whose tables are pc-relative words with zero relocations, and `bench/tier3.py`'s legend (B)/(C) rests on it — lifting
the flag is a project-wide perf lever over every switch-heavy row. THE BENCH: the Tier 3 table is a SERIAL prerequisite of `make test`
(21.5 s, +3.7 s this band; it could split across processes), and `test_tier3` re-measures every row the table already measured (≈2×
per row); the per-span poison exclusion is still band 3's. THE CONSOLE STAYS C: the escape's console bodies are `vt52.c`'s under the
existing Bconout(CON:) acceptances, so transcribing the BIOS console is a wave of its own and the lever for the 24 `own` rows and for
Bconout's. (T←)'s MEASURED LENIENCE: the ROM's ESC A-D and ESC J refuse a move through `beq.s $fc444e`, vq_chcells' `rts` inside the
escape's span, so 16 console cycles count as the escape's own on five rows (own 0.85) and a spill of 16 cycles or fewer could hide
there alone. `test_the_placements_are_what_the_search_finds` is gated by `RUN_SLOW=1` (48 s; no `slow` marker is registered). Bare
register numbers remain in six `.S` files (41 sites: `helpers.S` 3, `mouse.S` 11, `screen.S` 1, `raster.S` 15, `text_raster.S` 5,
`palette.S` 6) — `M68K_Dn`/`M68K_An` exist now. vdi_dispatch keeps ONE held record base (the ROM's A4) and walks the block and the
ptsin copy from a base masked once (the ROM's A5; the per-field form changed target code), which differs from per-field masking only
for a field within a record's size of the bus top, the I/O page; `next_of`/`handle_of` masked before the offset is the same edge,
unpinned host-only. UNPINNED otherwise: linea_dispatch's opcode-read-before-PC-step; vdi_gdp's record over LINEA_PTSIN and arm 8's
put-back through a re-read CUR_WORK (reachable only with CUR_WORK → 0, the vector page); the escape's column 0 with the cursor drawn
(past 1 MB even wrapped), zero-divide v_fontinit (vector 5), the real printer dump and an odd intin pointer — each a named host
refusal or unstaged. DRY left: `test_vdi_escape_transcription.py` keeps private `BENCH_ELF`/`table_entry`/`_anchor_of` (and
`test_vdi_escape.py` an `entry()`) that the shared modules now have (`BENCH_ELF` is `test/transcription.py`'s since the AES
foundation, and `test_transcribed.py`, was `test_vdi_transcribed.py`, uses it). WHAT A REBUILT ROM OWES (CODE /
TABLE entries in `test_vdi_rom_data.py`): vector $28 (stored from `$fc037c`) → `linea_rom_dispatch`; the `trap #2` door `$fc4ebc`'s
`jsr` and its $ffff answer (`$fc4ec8`/`$fc4ed6`) → `vdi_rom_entry`; `entry.S`'s `jsr $fca9f6` → an argument-less entry to the shipped
vdi_dispatch (the C core takes an image); the `$a009`/`$a00f` table longwords → entries with the Line-A convention; escape.S's `jmp`s
to `$fcb120`/`$fcb148` → shipped v_show_c/v_hide_c; the 71 function addresses of the opcode tables at `$fd372c`/`$fd37c8`, read in
place by `entry.c`; `fill.c`'s `LINEA_ROM_SEEDABORT_DEFAULT` (stored from `$fd08e6`) → the stub `$fc9f9a`, a LOCAL label in entry.S's
region (a global needs a table row); and entry.S's font table, whose three longwords stay the ROM's face headers (FONT_ROM_6X6/8X8/8X16).

**aes — the FOUNDATION's honest gaps: three mechanisms DESIGNED and not built, one assumption pinned as a refusal, and what
its gate PARKED.** The design note (the README's THE AES DOOR) covers what the gemstart, disp and forker ports need and nothing
builds yet: (1) THE LINE-F INIT COPY — gemstart's `Malloc(100)` (drop it and every later TPA block moves, the desk's globals at
`$143b4` included), the 100-byte copy of `$fee8c2` shipped byte for byte (its `movea.l #$fee900` and 38 bytes of the call table's
head are ORIGINAL ROM addresses kept as data, never relocated), and the `$2c` store under the ROM's condition; the copy's mask word
then differs from the original forever, by nature, and an init case drops the same window. (2) BLOCKING AND `switchto` — the
snapshot's `indisp = 1` makes `dsptch` a bare `rts`, a TEST LEVER and not the machine's behaviour; a real switch needs a checkpoint
at switchto's `rte` (`$fe395a`) through a `staged_call.h`-family hook, or a staged second process whose UDA `rte`s into a
`jmp ($2).w` sentinel stub, and savestate/switchto ship as byte-pinned `.S` (their saved register block is the oracle's CPU state,
a by-nature drop for a C twin). (3) THE FORKER MAPPING — forker's `jsr (a0)` on queued ROM addresses needs ONE hook of the
`staged_call.h` family mapping `AES_ROM_<FN>` → `aes_<fn>` (a pushed-long variant of the register/argument hook, not a second
hook), and the sixteen fork-function immediates (`aes.FORK_FUNCTION_IMMEDIATES`, kind CODE) join `test_vdi_rom_data.py`'s census
once their routines have a source file. PINNED AS A HOST REFUSAL: rc_intersect's C holds each GRECT pointer once and adds the
field offsets unwrapped, which differs from the ROM's `d16(An)` only for a GRECT whose last word passes the top of the 24-bit
bus — the host refuses that by assertion (`$fffffa`, `$fffffe`, as clip and as rect) and serves the last fitting one; the per-word
wrap that would model it measured 1.25–1.43, over the bar on every row. PARKED, each its own change: the `shipped-glue` make
target has no `$(ORACLE)` prerequisite (pre-existing); `tools/recreate_kit/kit.mk` line 105 is 184 columns (pre-existing, the
oracle link rule); `include/aes/aes.h` is included by no C yet (the scheduler's ports will); the Tier 3 splat of every registered
row is pinned (`test_boot_snapshot.test_every_registered_row_is_splatted`) rather than derived from `case.ROW_REGISTRIES`, since
deriving it would make row order depend on import order. The "general host WATCHDOG" band 3 parked now exists as the kit plugin;
the per-case `host_returns` bounds stay, since they name the case where the watchdog ends the process.

**aes — bands 0+1: one DIVERGENCE, what is deferred, and what the gate PARKED.** A DOCUMENTED DIVERGENCE: everyobj at a
level outside its two 8-word frame arrays — eight levels below `first`, or a climb above `first`'s level through a tree whose
object names its own sibling as ob_tail. TOS 1.02 goes on with a corrupted saved A6 and x[0] (ten deep, its return address)
or reads its own frame's y[7] and saved D7; C has neither to reach, so BOTH builds halt by name
(`recreate_not_reconstructed`: an `abort()` on the host, `trap #7` on target — `test_aes_oblib_walk.py` pins both, the target
by running the blob with the trap vector pointed at the sentinel) rather than write past `across[]`/`down[]`, which the
target build had done silently. The AES's own trees run four deep; a GEM program's tree eight deep under objc_draw is where
the two diverge. DEFERRED: newrect `$fe5cee` (w_getsize, band 2), rs_readit `$feaae2` and rs_load `$feac5c` (sh_find
`$feafbe`/sh_envrn, band 2) — all three ported in band 2 wave 1 — ob_change `$fea38e` (drawing); `gem_gemdos_call` `$fd9fc6` and the DOS glue's entry `$fe3ba0`
are UNOWNED (no reconstructed routine reaches them). UNPINNED: rom_rsc_init's failed Malloc (it copies the bundle to `$0`, the
Line-F vector included, so its own Line-F return runs data — no `rts` in 200,000 instructions; dos_alloc's own failure arm
is pinned directly) and its store-before-read order (only a block Malloc'd over the Line-F handler's RAM copy shows it).
AT THE BAR: dos_alloc's "no memory" row, 1.0993 — the C's DOS_ERR store is image-relative (`$98ec` is past a d16
displacement: 46 cycles against the ROM's absolute `move.w #1,$98ec`'s 20), which every AES core shares and no faithful
spelling of the C avoids; the lever, if margin is wanted, is that image-relative global store. THE STAGED-TRAP BATTERY RUNS
UNPOISONED (`test_aes_resource_dos.py`): the recording trap stores back the ledger pointer the attribution pass inverts, so
forced on, all 29 of its cases fail — cleanly now that the host twin refuses the wild pointer (G1), where it once crashed
or corrupted the worker. PARKED, each its own change: a kit `unpoisoned=` option (compare-but-don't-poison spans) that
would let 77 of gemrlist's 78 cases run poisoned with only the link longwords spared — moderate value, no surviving mutant;
moving `AES_RSC_BUNDLE` into `addrs.h` (it sits in `aes/resource.h` on `AES_LINEF_TABLE`'s precedent in `aes/aes.h`).

**aes — band 2 wave 1: one DIVERGENCE, two frame-overrun HALTS, one acceptance, and what the gate PARKED.** A DOCUMENTED
DIVERGENCE: sh_path builds an EMPTY PATH element by testing its CALLER's D6, which it never initialises. Every application path
enters with the dispatcher's `moveq #1,d6` (`$fe5da8`), and the C takes that 1 (`PATH_NOTHING_COPIED`, behaviour-identical to
0); the divergence is only sh_main's own sh_find (`$feb27e`), whose inherited D6 no C sees — a ROM-only case pins it (D6 = `\`
answers "APP.RSC" with no `\`). THE FRAME-OVERRUN HALTS: sh_find's and sh_envrn's frames are kept whole in host slots in the
ROM's layout, with the caller's saved A6's top byte past them (0 on a 24-bit bus). A string that lands a 0 on that byte is
served as the ROM serves it — sh_find's name part up to 22 bytes, sh_envrn's name up to 31, and a compare whose rewritten
length reaches the byte; at 23 / 32 bytes, or a nonzero byte there, BOTH builds halt by name (`sh_find: a name part`, `sh_envrn: a name` /
`a compare`; host-tested, the target's halt unexercised). What the ROM does there, pinned by ROM-alone cases: one byte past the
longest input it returns normally, handing its caller an A6 whose top byte is nonzero — the same frame on the bus, not the
caller's register (`$7900a2f4` for a caller's `$a2f4`); further bytes reach the saved A6's address bytes and then the return
address. ACCEPTED: gsx_moff's open nest at 1.23 (A) — 62 → 76 own cycles, the image pointer and `adda.l #$c86a` (above a d16)
being the C's floor; a byte-exact `.S` is impossible (the hide path's Line-F call word) and a (T←) `.S` would not be the ROM's
bytes. THE `glue` ROWS: vst_height's large font (1.02 own, 1.17 with its thunks) and gsx_moff's v_hide_c (0.95, 1.12) are
within the bar only net of the generated thunks, the (T→G) rule. PARKED, each its own change: (a) the GEMDOS HOST DISPATCHER
read an Fopen name without the 24-bit mask (`gemdos_strneq`, through device_named) — RESOLVED by the housekeeping pass of
2026-10-01 (`bus_byte` in `gemdos_strneq`; a tagged device name at the GEMDOS level and dos_open's tagged name; see band 2
wave 2's paragraph). (b) The `$a000` half of the bridge (gsx_mfsave's Line-A init: host
`require_cpu_routine($28, …)` + linea_init's C twin, target `.short 0xa000`) was designed and not built — no caller in this
wave; BUILT in band 2 wave 2 (`gsx_linea_base`). (c) Census rows owed by later slices: `$fe8844`/`$fe884a` (gsx_setmb's pushes of `$fed3e4`/
`$fed3be`, slice A — set in band 2 wave 2), `$fea08c` (ob_draw's push of just_draw, slice C), and the later bands' owners, marked `(ctx)`; R2's note
that `owed_by` is checked in one direction only (a port listing its routine as CODE but forgetting `owed_by` is not caught —
the reverse check would have to exempt GEM_TRAP2, which gsx.h compares but does not install). Not taken: an unlisted VDI
function surfaces as a memory diff rather than the hook's named refusal (R1; the case is still red); opcodes 28, 31, 33, 127
and 128 are reached from outside band 2 and are not yet in `aes_gsx.vdi_functions()`. EQUIVALENT MUTANTS: v_hide_c never
touches `$c86a` (no re-read), vr_recfl's colours and pointers have no alias, the clip's points are overwritten by the PTSIN
put-back before anything reads them, and DOS_ERR is already 1 when sh_find's store would set it; wrect's signed/unsigned
switch, everyobj's start x, and the fresh ORECT's second w_getsize.

**aes — band 2 wave 2: one acceptance, one row on the bar, the honestly unpinned arms, what is left to band 3, the ROM's
findings, and what the gate PARKED.** ACCEPTED: gsx_graphic's "the mode held" at 1.24 (A) — 58 → 72 own cycles; 72 is the C's
floor counted from its instructions (the image pointer plus a split displacement, `lea $6486(a0)` / `cmp.w $6486(a0),d0`:
16+8+12+12+8+16) against the ROM's `move.w/lea abs/cmp/beq/rts`; no `.S` is possible, since its other arms make the escapes'
Line-F call. ON THE BAR: gsx_tcalc's empty string in the small font, the cell too tall, 1.097 (prints 1.10, `through`) — if a
codegen drift pushes it over, trim its three bus-masked answer pointers. UNPINNED, each said in its battery: bb_set's straddle
of x = 0 (the `lsr.w` vs `asr.w` difference and the word count's wrap — the ROM's copy is `$f003` words wide, past the
oracle's 200,000-instruction cap; a right edge past `$7fff` and x = -8 inside one word ARE pinned); gr_box's thickness -32768
— REACHABLE (te_thickness, read as a word at `$fed22a`) but its 32,767 lines overflow the oracle's write ledger (shim.c
MAX_WRITES), the C's wrap checked by reading; gr_xor's count `$ffff` — unreachable (every caller hands it gr_scale's count, at
most 15); gsx_wsopen's `else if` — unreachable as an `if` (a 319 × 399 answer v_opnwk never gives); gsx_start's ncols/nrows
`divs` overflow — needs a cell width of -1 from the VDI (a font answer, not stageable without fabricating a font; gl_wbox's
overflow IS pinned); v_opnwk's ARRAY pointers tagged — PINNED since the housekeeping
fix below. LEFT TO BAND 3: gr_clamp (`$fe86dc`, with its fragment `$fe86c2`), gr_draw (`$fe8532`) and gr_xdraw (`$fe8564`) are
reached only from the interactive loops (gr_rubbox/gr_dragbox, gr_wait). A FORWARD HAZARD (R4#6): gr_watchbox (`$fe84ca`,
still the ROM's) reads gr_setup's `move.l #$98a4,-(sp)` immediate at `$fe85b2` AS DATA (gl_rscreen; census CODE_BYTES in
`test_aes_rom_data.py`). gr_setup is now C: a rebuilt ROM linking it at `$fe85b0` no longer holds those bytes, and the ROM's
watchbox would read garbage — band 3 must port gr_watchbox with the value (`AES_GL_RSCREEN`), or gr_setup must ship its ROM
bytes until it does. ROM FINDINGS (pinned): gl_mlen (`$c920`) is read by gsx_mret and written by nothing in the AES (GEM's
gsx_malloc set it), so the save buffer's length is always 0; `$c916` is a seventh attribute cache gsx_start fills with -1 and
nothing reads; gsx_setmb's third argument (`$947a`, GEM's `&drwaddr`) is pushed and never read; gsx_graphic's into-graphics arm
is never taken by the ROM (its callers are the start-up, mode held, and the shutdown, into alpha); v_show_c(0) FORCES the cursor
shown (`$fcb12a`), v_show_c(1) counts down one; gsx_start's second vst_height discards its four answers into one stack word and
reads ptsout[1] twice; bb_set's word index is a logical shift (a rectangle straddling x = 0 makes a ~61,000-word form, latent);
gsx_malloc's buffer is `$3400` bytes, never checked; gsx_chkclip counts x+w (y+h) EQUAL to the clip's edge as touching
(`blt`); gsx_tblt never sets the block's PTSIN (v_gtext reads it as the last call left it); bb_fill passes gsx_attr the text
colour's own cache, so only the writing mode can change; gsx_tcalc's count is xstrpix's BYTE count (a string of 256+ wraps);
gr_box's negative thickness draws -t+1 lines (`subq #1` first); gr_scale counts `lsr.w` of x+y (-32768 gives 15 steps);
gr_gicon pushes an extra word (2) under gr_gtext's frame, GEM's dropped `tmode`; register hygiene with no observable bug
(gsx_trans clobbers D3, gsx_sclip A2; gr_movebox/growbox/shrinkbox restore only what they use). RESOLVED by the housekeeping
pass of 2026-10-01 (Tier 3 table byte-identical: the mask is free on target, where `bus_dereference` is the identity; helpers.o
and workstation.o are identical objects, and fs_drive.o's `gemdos_strneq` only swapped its compare's operands (`move.b
0(a1,a2.l),d2 / cmp.b (a0)+,d2` became `move.b (a0)+,d2 / cmp.b 0(a1,a2.l),d2`: the same 6 bytes and 22 cycles, so its row did
not move): THREE HOST BUS-MASK GAPS, each a guest pointer read as `image + pointer` where the 68000 drives 24 bits — (a)
GEMDOS's Fopen name (`gemdos_strneq` now reads through `bus_byte`; a tagged device name at the GEMDOS level, dos_open's tagged
name; RED first, a SIGSEGV), (b) the VDI's `vdi_init_wk` reaching the open's CONTRL/INTIN/INTOUT/PTSOUT (`bus_word` /
`set_bus_word`; a tagged-arrays init_wk case and its host-only twin in a child process, v_opnwk's tagged work_in / work_out /
both; RED first, a SIGBUS), (c) the VDI's `vdi_vr_trnfm` reading contrl, both MFDBs and both forms (bus accessors; each form's
BASE masked, its walk past the top of the bus not modelled — said at the core; tagged-everything cases both ways and in place,
their host-only twins in a child process copy and in place, two forms differing only in the top byte COPIED over each other as
`cmpa.l` says, and gsx_trans's tagged source / destination / both). (c)'s cases came AFTER its fix, so its RED is the strict
mutation sweep, each mask reverted in a private build: 8 of 15 KILLED outright, 1 equivalent (strneq's right operand is always
the ROM's device table); the 6 that fault the host (init_wk's contrl and answer stores, vr_trnfm's MFDB pointers, `stand` store,
copy destination and in-place base) now FAIL a named child-process case — all 6 KILLED under `-n 4` as `make test` runs them,
and all 6 by the child cases alone; run serially over whole files, 5 of them still end the process inside the in-process
differential case (ABNORMAL). And the BUILD RULE: kit.mk's two compile rules now depend on every header under `include/` at any
depth (`PROJECT_HEADERS`, a `find`, dotfiles left out so an editor's dangling `.#x.h` lockfile cannot stop make); this project's
one-level `COMPONENT_HEADERS` patch is gone. The parked claim was half stale — that patch already rebuilt the `.so` for
`include/aes/gsx.h`; only a third level was uncovered (proved both ways with `make -n`). STILL OPEN, the same class: a TAGGED
NON-DEVICE Fopen name reaches the file system's path walk (`src/gemdos/fs_drive.c` / `fs_name.c`, raw `image[...]`) and SIGSEGVs
the host — the GEMDOS layer's convention is to assert a pointer inside RAM rather than mask it, so masking the name walk is a
layer-wide change of its own; and the VDI's other raw caller-pointer sites (band 4 counted ~90; a census by pattern finds 60, a
LOWER BOUND — pointers carried under other names in arcs/lines/blit escape it: `inquire.c` 16, `mouse.c` 18, `text.c` 7,
`attributes.c` 5, `escape.c` 5, `gtext.c` 3, `palette.c` 3, `fill.c` 2, `vdi.c` 1), which no AES caller reaches with a tagged
pointer today. New VDI code reaches a held caller pointer through m68k_idioms.h's `bus_word` / `set_bus_word`
(`include/vdi/vdi.h` says so). Known open in the tests: slice A's
`test_aes_gsxif.py` still spells the stale two-MFDB dict inline (`aes_gsx.GL_MFDBS_STALE` exists) and its STALE_ANSWERS over
`gsx.ANSWERS_AT`. EQUIVALENT MUTANTS: gsx_malloc's fix after the trap (neither reads the other's writes), gsx_start's planes
loop as `while (c > 1)` (floor(log2) for every word), gsx_mfset reading ad_intin before the hide (v_hide_c never touches it),
gsx_blt's moff after gl_dst's fix (v_hide_c reads nothing gsx_fix writes).

**aes — band 2 wave 3: the cells real data cannot reach, one retracted finding, what the bindings owe, one row over the
bench's cap, the ROM's findings, and what stays out of scope.** STAGED ON REAL OBJECTS, because no tree the snapshot holds
carries them (each said in `test_aes_just_draw_staged.py`): FTEXT, USERDEF, SHADOWED, CROSSED, an IBOX border, the small
font, HIDETREE and an ob_spec of -1 (no AES writer of either found), types outside 20..32 (19, 33, `$7f`: both tables fall
through), and a raw text not starting '@' (seeded by the ROM's own inf_sset — every raw text in both resources starts '@').
TITLE+SHADOWED is pinned on the DIRECT shores only (it reads an unset frame word, which differs on target and through
Line-F; staged at the ROM's -2(a6) and the C's slot word alike) and is not priced. TEXT IS NOT APP-ONLY — RETRACTED: J's
finding that tree 2's TEXT (obj 2, TEDINFO `$d18c`) has te_ptext -1 and no writer was wrong. sh_draw (`$feada0`) stores the
shell's command through ad_pfile (`$c7a2`, set at `$feb102` to `*(ad_stdesk + 60)` = that ob_spec; ad_stdesk `$c820` = tree 2)
at `$feadca`, right before `ob_draw(ad_stdesk, …)` under gsx_sclip(gl_rscreen); its callers are `$feaddc` (objects 1..2, depth
0), the launch path (`$feb1a8`/`$feb24c`/`$feb350`/`$feb366`/`$feb384`: ROOT, depth 1, the shell buffer `*$c79e`) and `$fee460`
(`*$c6e6`), gated by `*$9b2a && !sh_dodef` — off at rest in the snapshot, so the -1 is the resource's placeholder until the
first launch. Both batteries now draw it as sh_draw leaves it. WHAT THE BINDINGS OWE (R3 F3): ob_draw and ob_change are void
and so are the C cores, but the ROM leaves D0 defined and the bindings `$fde2fe` (ob_draw, in `$fde2e8`) and `$fde32c`
(ob_change, in `$fde30e`) store and return it: gsx_mon's D0 (1 unless the nest reaches 0 and gsx_1code runs), or on
ob_change's three early returns the OLD state word (`$fea3c4`–`$fea3c6`). A port of those wrappers must not assume a defined
answer, or must model this. OVER THE CAP: the selector's whole draw (256,140 instructions, the longest ROM run in the battery,
re-measured by `test_the_budget_covers_the_longest_draw`; `OB_DRAW_INSNS` is twice it) cannot be a Tier 3 row — `emu.run`'s
default 200,000-instruction cap serves the bench and the snapshot sweeps; priced in a scratch run with the cap raised at 0.83
own, 0.94 with glue. UNPINNED: ob_format lengths ≥ 32768 (a word strlen and word steps; no buffer reaches it); ob_user's read
order of ub_parm/ub_code against rc_copy/gsx_gclip (those callees write only the frame, which differs between the shores);
ob_change's `clr.w 16(a6)` writes the CALLER's argument slot, which no caller reads back (gr_watchbox's loop re-pushes all four).
The adapter's dropped `ext.l` is equivalent under GCC (the m68k callee re-extends an `int16_t` from the slot's low word); a
compiler trusting a sign-extension ABI attribute could break that, so the `ext.l` stays. ROM FINDINGS (pinned): ob_format stores
its output's end pointer at -4(a6) and never reads it, tests '@' BEFORE strlen(tmplt) (a raw text that is also the template
empties it) and stores the NUL at `out + strlen(tmplt)` before the walk (an overlapping raw text reads it back); ob_user passes
(curr, new) as one longword from 22(a6) (pb_prevstate = curr, pb_currstate = new); a SHADOWED G_TITLE reads its border colour
from an unset local (-2(a6): no crack, no BUTTON — TITLE is the only type with a non-zero border and neither); gl_width/8
(`divs`) is computed for gsx_blt and ignored by gsx_fix's screen arm; just_draw's clip-word test is redundant (gsx_chkclip
answers 1 for an empty clip); G_STRING's rows in both jump tables are dead (STRING branches to the label at `$fe9b2a` first);
IMAGE/ICON/USERDEF/TITLE/outside types never initialise the colour locals -2..-10 but tmode/tcol (only the TITLE case is
observable); the packed longwords carry and borrow — OUTLINED's corner at y<3 (the desk's own dialogs sit at (0,0) before
form_center), CROSSED's far corner at h=0 (y = 0) and past y+h-1 > `$ffff`, ICON's GRECTs when ib_y+y overflows; only
SELECTED is inverted by ob_change (another bit changing with it waits for a redraw); ob_change ignores ob_user's answer; an
ICON's change is always a full just_draw; the XOR inset is one `add.l` (y in [-th,-1] carries into x); ob_draw never reads the
root's ob_next; ob_change's early returns skip moff/mon. gl_font (`$980c`) has exactly two writers, gsx_start (`$fdaace`, -1)
and gsx_tblt (`$fdad4a`, after its own vst_height): a cache of the VDI's face, so (3, small) is unreachable. OUT OF SCOPE,
noted only: `aes_resource.header_of` duplicates `aes.resource_header(application_global=…)`, and `aes_objdraw.object_long`
keeps a (tree, index, name, image) argument order where `aes_objects.object_word` takes (image, tree, index, name).
EQUIVALENT MUTANTS: clip-w-only / clip-h-only (gsx_chkclip answers 1 on an empty clip; the skipped work writes only the
dropped frame), image-row-16 (gsx_fix's screen arm never reads it), marks-always / marks-low-byte (with no state bit the
block only shrinks or negates frame words), label-chars-byte (xstrpix counts a byte), userdef-state-low-byte,
shadow-after-neg-signed; the adapter's dropped `ext.l`.

**aes — band 3 wave 0: the door's entries not yet wrapped, the arms no reachable state pins, what differs by nature, the
equivalent survivors, and the ROM's findings.** NOT YET IN THE DOOR: ev_button (`$fe68a4`), ev_block (`$fe6874`), tak_flag
(`$fe4e5a`), unsync (`$fe4eb8`), ct_chgown (`$fe49ba`) and post_button (`$fe52e2`) — each becomes one wrapper, one `ENTRIES`
line and one census line when its first user lands (W2 / G / M); (EV) needs no change. Wave 1 wrapped all but ev_button (M's). REFUSED, NOT ROWS: every wait nothing
in the machine satisfies (gr_stilldn waiting on an event that has not happened) reaches the dispatcher and is refused as
"would block" — the "no event" answer the snapshot's indisp = 1 used to give is a state no process sees. UNPINNED: gr_watchbox's
0 answer — the loop ends only on the button's rise, which is the mouse interrupt's: over the button up it ends in pass 1, over
it down pass 2's wait blocks (pinned up to there: the object drawn `out` and both frames, against the ROM's run stopped where
it blocks); pinning the answer needs a rise at a chosen poll (a kit "store at the k-th read" of the button through the
nested runs). ap_rdwr's non-zero answer: 0 in every reachable machine (PD0
parked, running, a second message, a merged redraw, to PD1); a send to a process id with no PD spins in the ROM. w_nilit's
negative count (round the word over ~1.5 MB): every caller passes 19 / 8 / 19. The held w_move's D0: the ROM leaves the
CALLER's (pinned), the C answers 0 and is not compared — the arm is unreachable from draw_change (`$fec172` returns first),
and the Tier 3 row "drawing held, moved" compares no answer (`aes.register(answer_compared=False)`). find_pos's first walk reading the image instead of
the bus (mutant bus-find-first) is caught only by a host SIGSEGV on the tagged case — ABNORMAL, not counted killed.
UNPOISONED, each measured: every door case (the attribution pass inverts the fork queue, CDA and EVB links — the poisoned ROM
gr_stilldn did not return within 200,000 instructions; stale staging stands in), curfld's stretch redraws (PTSIN read first),
w_owns' link re-read, w_cpwalk's rebuild, wm_get's NEXT (it reads the cursor it writes). BY NATURE: the BIOS trap's register
save under the event layer's keyboard poll (`$8de..$905`, D3-D7/A3-A7 of the CALLER — gr_watchbox's D4 reaches it through
ev_multi) is dropped by name in Tier 1 (`TRAP_SAVE_DROP`, the PC and SR after it still compared); priced rows move savptr into
the stack band (gemdos.machine's arrangement). ct_mouse's re-show contrl[3] (the ROM's never-written -2(a6)) is dropped by name
over a staged stack word and compared whole when the stack holds the C's 0. EQUIVALENT MUTANTS: ap_sendmsg's answer dropped and
rlr masked to 16 bits (every PD lives in THEGLO below `$10000`); the door's zero specialisation applied always (no caller
passes a non-zero second rectangle, timer or message: byte-identical today); check's '9' upcased (STNUM is digits), its word
validation index and unsigned upcase (`set_of` takes an `int8_t`, aes_toupper re-casts the low byte); w_drawdesk's depth 7 vs
8 (everyobj descends from level 8 only after the level-8 store that corrupts its frame: 6, 7 and 8 agree on every tree that
returns), w_bldbar's `bar != W_HBAR` (its only caller passes 9 / 14), w_move's strip width and strip sclip (w_cpwalk →
w_clipdraw re-clips per piece — equivalent UNLESS the 80-ORECT pool is exhausted and the top window's list is empty),
w_move's strip use_true 1 (the window IS gl_wtop), wm_find's depth 1 (window objects never get children). ROM FINDINGS
(pinned where reachable): ct_mouse(0) hands gsx_ncode TWO words where it takes three (`$fe4afc`; harmless — v_show_c reads
intin[0], itself stale); ap_rdwr MERGES a second WM_REDRAW for a window already queued (a different window appends); a message
to PD1, the screen manager, lands in its PIPE (its parked EVBs are not a pipe read); gr_watchbox saves D2-D7/A5/A6 but restores
D4-D7/A5/A6 — its D2/D3 save slots ARE its rectangle; check upcases 'f' and 'p' too (only '9', 'a', 'n' clear it) and calls
rs_str before reading the character; the validation stretch is bounded only by te_tmplen (> 81 writes into fmtstr) and lstcpy
counts in a byte (255+ characters: the stretch skipped, the NUL at VALSTR[-1]); find_pos reads past the template's NUL;
ins_char's room is SIGNED (≤ 0 stores below the string); bfill's fill pushed as the word `$3920`; a refused typed key leaves
the frame's start stepped back and D3 un-stepped; pxl_rect stores gr_just's count at -10(a6) and never reads it; a NUL key is
never validated; every EDCHAR copies the raw text back (a fresh '@' text is emptied); "ob_draw never returns seven levels
down" is band 1's everyobj divergence counted from the START object (level 8 = the store into its saved A6; everyobj returns,
ob_draw's own return runs away); `$c940` holds window drawing (wind_set field 13 with a non-zero handle; w_clipdraw and w_move
do nothing while set, draw_change returns early); wind_get fields 13 and 14 have no arm; w_obadd IS ob_add's body; w_strchg's
store is dead for every window but -1, w_move's strip clip is dead, w_bldactive adds the saved x,y then overwrites them
(`$febcaa..$febcbe`); wm_create reads window 8's flag byte `$c66f` when all 8 are in use; wm_delete and wm_calc leave D0s the
desk's bindings store (`$fde3f6`, `$fde4f4`); gl_wbox is 12 in the snapshot (gl_hbox 11). OUT OF SCOPE, noted only: wrect.c's
w_getsize and wmlib.c's `grow_extent` spell "w,h += W_BORDER" twice (folding them would move objects); `aes.run_function
(answer_compared=False)` is new shared machinery with one user.

**aes — band 3 wave 1: the interrupted rows' Tier 3 (DEFERRED; RESOLVED in wave 2), the arms no reachable state pins, one target divergence,
the equivalent survivors, and the ROM's findings.**

RESOLVED IN WAVE 2 (it was DEFERRED, wave 2's first step): TIER 3 PRICING OF INTERRUPTED ROWS — the kit change below landed as K's foundation, and the rows are priced and fully vetted (the band 3 wave 2 paragraphs above and below). As it stood after wave 1: the cases delivered through `aes_event.interrupted`
are verified at Tier 1 only. A door row's Tier 3 makes FOUR ROM runs, and only two of them can be handed a delivery today:
`_original_windows`, and our blob's DoorWindows. The other two cannot:
- `RomBench.measure`'s own ORIGINAL (`_both_sides`) is an unwatched `emu.run`. An interrupted row's original BLOCKS there
  (measured: no return within 1,424,474 instructions). That run is also the one the image, return, stream and odd-access
  comparisons are made against, and its write ledger is what `vet_dropped` checks the mask word against.
- `tier3._original_own_cycles` and every VERIFIED_CASES consumer in test_boot_snapshot (the noise test and the
  unmodelled-I/O sweep) replay a row unwatched too.

Landing it needs a KIT CHANGE: `RomBench.measure(original_watch=)` (the original run by `run_bench` + `watched`), a write
ledger after a bench run, and a `delivered` field on VERIFIED_CASES, consumed by those sweeps, tier3's Row,
`_original_windows` and `_original_own_cycles`. The finishing agent prototyped the design in scratch. It laid the delivered
bytes in at the k-th door entry at zero cycles in all four runs, and every tier3 assertion stayed live; only `vet_dropped`
was stubbed. RED in the prototype: delivered on one side only, either side, or one call late on ours.

These own ratios are MEASURED IN SCRATCH, NOT REGISTERED (whole run in brackets), every one far under the bar:
- mn_do: a DISABLED item clicked **0.63** (0.95), an item chosen 0.61 (0.94), an item's child under the mouse 0.62 (0.94),
  the menu left then a click off it 0.58 (0.93), press-drag-release 0.59 (0.93), the DISABLED-alone loop left by the mouse
  0.42 (0.70);
- gr_dragbox: moved with the cursor shown **0.80** (0.99), moved then released 0.79 (0.98), moved twice out of its bound
  0.79 (0.99);
- gr_slidebox: the elevator dragged **0.75** (0.97);
- gr_rubbox: stretched, and its busy loop left by the release, 0.79 (0.98);
- gr_rubwind: stretched 0.80 (0.99);
- gr_wait: released, or moved, while it waits 0.82 (0.99).

The bold three would become their routines' WORST rows: mn_do 0.63 against today's 0.61, gr_dragbox 0.80 against 0.78,
gr_slidebox 0.75 against 0.71. To register once the mechanism lands:
- mn_do's DISABLED-item, item-chosen, menu-left, press-drag-release and DISABLED-alone rows;
- gr_dragbox's moved-twice and cursor-shown rows;
- gr_rubbox stretched, gr_slidebox dragged, gr_wait released.

Dropped as duplicates: the child-under-the-mouse row, dragbox moved once, rubwind, and gr_wait moved. (Wave 2 registered each routine's WORST only — mn_do 0.63, gr_dragbox 0.80, gr_slidebox 0.75, gr_rubwind 0.80; the rest, measured again, were none over its routine's worst.)

UNPINNED, each with its reason:
- **bar-height-wchar** (mn_bar's desk box height in gl_wchar instead of gl_hchar). Every machine is the snapshot's low
  resolution, where both are 8. A COMPOSED high-resolution workstation (the ROM's gsx_wsopen(high) + gsx_start over the
  low-res snapshot) is a MIXED machine no ST produces: mn_bar over it writes 216 B below the screen base in a 160-byte
  stride, over the MASKed boot-noisy stack under _memtop. A real resolution switch is not derivable: Setscreen with a change
  of resolution halts, and console_reinit is not reconstructed. The case was dropped.
- **post_button's two words swapped** (door-post-words-swap, and the target twin post-words-swap). The only C caller,
  mn_bar, hands (1, 1). The ROM's other callers, bchange `$fe51d8` (`$c90a`, clicks) and set_mown `$fe504a` (`$c90a`, 1),
  are band 4's. It is pinned when a C caller handing button ≠ clicks lands, with no test-only export. The target's
  post-no-d2-clobber is latent the same way: nothing is live in D2.
- **evdoor_ev_block's TARGET wrapper** (`include/aes/evdoor.h`: push A0, push the code word, `jsr`, `addq #6`) is executed
  by NO surface. ev_block always blocks (`NEVER_ANSWERED`), so no Tier 3 row runs it. Its push order and frame size are
  unpinned on target; the host door's frames are compared.
- ev_block's parameter read from `ad_windspb` (`$c83e`): equivalent over every reachable state, since it is written once,
  at `$fda032`, to `$9aee`.
- RESOLVED in wave 2, both: the full vets by every returning interrupted case's second differential inside `aes_event.interrupted` (by construction, 56 cases), and `keys()` on the in-place delivery path (K4). STILL DEFERRED: the per-worker fork server. As it stood: DEFERRED to band 3 wave 2 (code-review gate): the C side of an INTERRUPTED case (`aes_event.interrupted`) runs in a child
  and skips the full differential's vets — registers, odd access, write ledger, refusal tallies — so mn_do's later passes
  and every drag step after the first are held to the image + answer + handed-frames bar only; closed by wave 2's Tier 3
  interrupted-row kit change, which runs both sides through the bench. Also deferred: `keys()` onto the in-place delivery
  path (wave 2's form loops type keys), and a per-worker fork server for door children (363 children per suite run after
  wave 1's guards; each costs ~84 ms to start).
- Arms verified at Tier 1 and priced by no row, because each is no routine's worst: ev_block's wait (it blocks),
  window_below past one sibling, WF_HSLSIZE / WF_VSLSIZE / WF_INFO, and WF_TOP of the window already on top.
- The overlapping-window shapes over windows with EVERY gadget pass the bench's 200,000-instruction cap. Their arms are
  priced over title-bar windows.
- mn_register(-1) with 14 or more characters: the ROM's lstcpy overruns its 14-byte frame into the saved A6 and the return
  address, while the C overruns its host slot into the neighbouring slots and carries on. It is a divergence only where the
  ROM itself crashes, so it cannot be pinned.

A TARGET DIVERGENCE, unmodelled by design. wind_set, wind_open, wind_close and wind_update(END_UPDATE) can return with the
application still holding the lock (count > 0). There the ROM's unsync leaves its CALLER's D0, while the target C returns
whatever GCC left in d0 before `EVDOOR_CALL_LONG` (an `=d` output, undefined on entry). The bindings store D0.w into
int_out[0]. Those cases and rows do not compare the answer (`answer_compared=False`).

EQUIVALENT SURVIVORS:
- W2's 13:
  - ct_chgown never reads `$9b26`;
  - gl_wtop is -1 or a handle;
  - w_getsize writes two distinct frame slots;
  - the window tree has two levels (everyobj depth 1);
  - whole = 0 with gl_wasclr = 1 is unreachable (×2);
  - the "old inside the new" shortcut leaves the same state as the union (×3);
  - the old top's w_cpwalk is overdrawn by the redraw that follows;
  - w_cpwalk(-1) draws nothing;
  - wm_set's D0 0 (unsync's release answers 0, the held arm uncompared);
  - ct_chgown's D0 0 (post_button's walk end, 0, always).
- G's 3:
  - slide-no-room-test (room 0 makes rc_constrain put place at 0, short of an object ≥ 32k pixels wide);
  - do-set-title-clear (menu_down re-selects: the same screen and state);
  - bar-no-unlink-head (ob_add sets head when tail is NIL).
- Target: wmupdate.S's adapter without `ext.l` (GCC's callee reads the slot's low word).

ROM FINDINGS (pinned where reachable):
- An UNBALANCED wind_update(END_UPDATE) DEADLOCKS. The count goes to -1. The next BEG_UPDATE's tak_flag sees 0 ≠ 1 and no
  owner, and refuses; amutex refuses again; unsync from a negative count never reaches 0. Every later BEG_UPDATE of every
  process blocks forever.
- unsync with a waiter HANDS THE LOCK to the waiter's PD (count 1), zombies its EVB and calls dsptch with the caller still
  ready, which is a YIELD. With the count still above 0 it leaves its caller's D0.
- tak_flag's refusal clears only D0's LOW word.
- ct_chgown answers 0 always.
- fm_own's give-back restores the KEYBOARD owner first.
- draw_change's tail overwrites the CALLER's rectangle with the new top's, and its "old inside the new" test is redundant.
- wm_opcl reads WS_PREV through the caller's pointer after draw_change.
- wm_set's slider arms read four globals into dead locals.
- mn_bar stores the menu owner's pid as a sign-extended LONG at `$9730`, which the screen manager reads as a WORD: the high
  half, so menu messages always go to pid 0. Its fake click post_button(ctl_pd, 1, 1) is counted in `$c6cc`, which the
  screen manager swallows.
- mn_register(-1)'s copy is unbounded.
- pd_nameit is unbounded and strscn writes NO NUL: 8 characters before the '.' leave p_cda whole, a 9th lands alone on its
  top byte (ignored by the 24-bit bus), and a 10th and more change the pointer.
- mn_do reads `tree[-1].ob_state` when ob_find answers -1 and tests DISABLED by EQUALITY with 8. A SELECTED + DISABLED title
  is dropped, then do_chg refuses it; a title DISABLED alone busy-loops until the mouse moves.
- menu_sr widens its saved rectangle 1 left and 2 right / down.
- gr_rubwind's and gr_dragbox's gr_setup colour is the word they pushed for wm_update(1).
- gr_dragbox's corner +1 is word by word.
- gr_slidebox's mul_div runs only when the room is non-zero.
- gr_wait's two-box flag is rc_equal's D0 with bit 0 flipped: a twin unless poff EQUALS gl_rzero.

RESOLVED DEBT: the host slots' 64-bit held mask (60 of 64 bits used after this wave) is now a byte array,
`host_slots_held[HOST_SLOT_ID_COUNT]`, with no ceiling; every suite is unchanged.

OUT OF SCOPE, noted only:
- A header's constants are read two ways: mnlib.h through `aes.AES_HEADERS`, grdrag.h and wmupdate.h through
  `aes.header_constants`.
- `aes.register` stages each row three times and runs a ROM run per row for the settled mask word. Making that lazy would
  save up to ~1.2 s of import per AES battery.

**aes — band 3 wave 2: what stays unpinned, one deferral, the equivalent survivors, and the ROM's findings.**

UNPINNED, each with its reason:
- **eralert past 6.** The critic handler crit_err (`$fe3cbe`) maps ~error through the byte table `$fef790`, but its byte
  move keeps ~error's HIGH byte: a BIOS error <= -257 reaches eralert as `$01xx`, and a positive one passes the signed
  `ble`, indexes below the table and arrives as `$FFxx`. Both index past eralert's tables (error 7's string word is
  `$0102`, its level read from `$fefa30`); such runs walk garbage trees and are REFUSED BY NAME (a walker's depth, or a
  blocking door call), so they cannot be pinned.
- **The over-cap alert shape.** Five 31-character lines with three 10-character buttons run 200,973 ROM instructions
  (208,880 with the cursor shown; 20-character buttons 280,007), past the bench's 200,000 cap. Named in the battery and
  priced by its neighbours (four lines + three 10-character buttons 0.68; five lines at the cap with short buttons 0.68).
- **The two longword store-refusal mutants** (ram-long-unchecked, ram-long-as-word): a longword store within 3 bytes of
  the top of RAM. No form routine stores a longword through a caller's pointer — the long stores the fm cores make go into
  trees and frames — so the battery cannot reach it. A pin belongs to a battery whose core does (ob_getspec's answer,
  shell_find's, gsxif's).
- **The 39-key typing session.** fm_do typing 39 keys into the path field measured 749,695 instructions (3.7× the cap;
  each key ~15–19 K). It is priced PER KEY SHAPE (the long path's Backspace / a key / Left-Delete / Escape, the empty
  field's moves), each under the cap; the whole session is Tier 1 only. RESOLVED IN WAVE 3: a 38-key session is
  priced by its slices under a declared budget (five rows, the last character typed 0.77, fm_do's worst), and the
  partition test holds every key between them at or under it.
- **The two chip-declaration mutants** in `aes_event.parked` and `_continued_at` (FK's parked-no-chip-declared,
  continued-no-chip-declared): equivalent today — the parking path (ev_multi / wm_update into dsptch) reads no PSG or
  named hardware, and the interrupt run in between is an `emu.run`, which already declared nothing. Both calls are kept;
  the mechanism is RED-pinned at the kit level.

STILL DEFERRED: the per-worker fork server for door children (the children per suite run grew again with wave 2's
batteries — fmalert 95, fmdo 67 per R4's count). Also deferred by the code-review gate, each with its measured reason:
a per-row derivation budget for long interactive rows (fs_input ~443K instructions) instead of raising the global
DERIVATION_INSNS — DELIVERED in band 3 wave 3 (`budget=` / `cap=`, held both ways);
splitting bench/tier3.py's measuring half from its import-time row registries
(the first tier3 import in a battery-only worker costs ~10.8 s; under `make test` it is already paid, and a lazy import
would cache a partial module); and re-measuring the boot snapshot's MASK from repeated captures (`--twice`): two fresh
captures each differed from the stored snapshot outside the MASK at a few different small spans (e.g. `$4a5`,
`$16aa..$16bf`, `$8920..$892d`) — the suite is green over both, so no verified case reads them, but the MASK is not proven
complete.

EQUIVALENT (or unreachable) SURVIVORS:
- fmlib.c: following-unsigned (the follower is compared only with ']' / '|', both below `$80`, and kept as a byte);
  build-no-min and build-row-unsigned UNREACHABLE (each needs a 5th button or 10th line, which faults first);
  fq-cda-once, build-hchar-unsigned, dq-front-unsigned, keybd-key-unsigned-ok (equivalent on every reachable machine: dq
  never writes gl_cda; hchar 8 or 16; the front 0..7; every table key below `$8000`).
- fmdo.c: r-all-taken (ob_change returns at once on an unchanged state, `$fea3ca`, before any store); d-init-no-clear
  (`next` is rewritten before anything but the loop-top test reads it, which treats 0 and the edited field alike);
  a-no-outline (tree 1's root is `$10` in the resource and nothing but fm_alert writes its state); a-shallow (the alert
  tree is one level deep).
- m68k_idioms.h: ram-word-as-byte (a word store is even after the odd-address refusal, so the two bounds refuse the same
  addresses).
- K: interrupting-unseeded (a delivery's found / wrote never touches the trap save or the stack band; the compared replay
  is seeded).

ROM FINDINGS (pinned where reachable):
- fm_strbrk bounds neither lines nor buttons: objects up to 10 reproduce (a 6th line into button 1's buffer; a 4th button
  into AES tree 2's root, its G_BOX colour word `$00001143` taken for a string pointer, the text at `$1143`, the root then
  made a SELECTABLE\|EXIT\|LASTOB button by fm_build); object 11 (a 5th button or 10th line) has ob_spec `$00ff1100`,
  above RAM — the ROM's store is lost (an ST bus-errors), the C refuses it by name.
- Button buffers are 11 bytes against the 31-character cap: a longer button runs into the next one's, the third's over
  the free string "PATH=" (`$d9af`).
- A doubled delimiter AT the cap keeps its second as a delimiter; a NUL-ended line goes on by the byte after the NUL;
  "a\|]" makes one more, empty, line; fm_parse's icon is `str[1] - '0'` signed and unchecked.
- find_obj with `which` outside 0..2 answers the first EDITABLE from object 0 itself.
- fm_keybd: Return with no DEFAULT stores 0 and goes on; a key word >= `$8000` never matches (the key is sign-extended to
  the table's longs); the table is 7 keys-or-0 then 7 labels, the 7th shared by key 0 and every unmatched key.
- fq flushes gl_cda's queue (the running PD's), chkkbd fills gl_kowner's; dq checks no empty queue (its callers guard).
- The bell (`$fe3a0c`) is BIOS Bconout(CON:, BEL) by `trap #13`, not GEMDOS Cconout through `$fe3c28` (fs_active's).
- A press held off a dialog spins fm_do (a bell per pass until the button rises; no return in 1.5 M instructions).
- ev_button runs no forker before it waits: a release the AES has not taken BLOCKS it — a radio button held down blocks
  the dialog in ev_button (a SELECTABLE object's rise is taken by gr_watchbox's ev_multi first).
- fm_button's `andi.w #9` (`$fe7454`) is redundant.
- A key and a press in one ev_multi: fm_button's verdict overwrites fm_keybd's.
- An alert has no field: a typed key that is no move key goes to ob_edit on the ROOT, fm_do's index word never set.
- fm_dial's D0: the type, gsx_mon's 1 / 0, or w_clipdraw's held 1; w_drawdesk widens the caller's `big` by 2 × 2 in place.
- fm_alert checks no default. One past the buttons sets DEFAULT on a non-button object, so Return finds none and the
  alert waits for a click; 4 on a three-button alert writes DEFAULT onto object 10 = tree 2's root (`$cff4`, R3).
  FORM_ALERT(-1, …)'S SIDE EFFECTS (R3, pinned): a negative default sets DEFAULT on a message line of the AES's SHARED
  alert tree, where it stays (fm_build resets only the buttons' flags) — every later alert's Return answers -1, fm_error
  answers 1 and eralert(3) Retry where a clean tree answers Cancel; and a later alert with FEWER lines hangs on Return on
  both sides (ob_change of the unlinked object never returns).
- fm_error: above 63 it shows nothing and answers 0; a negative code shows "TOS error #" with the word unsigned (-1 →
  #65535); "TOS error" hands merge_str the address of fm_error's own argument word.
- eralert's tables are indexed unchecked (above); crit_err keeps ~error's high byte.
- The dispatcher's default arm (aes_unimplemented `$fe64a6`) is fm_show(27 "Bad Function #", NULL, 1).
- ev_button's answers are four words (`$fe681a`): the mouse (the click's own when one was counted, clearing `$c836`), the
  buttons `$c792`, the shift keys `$c72a`.
- THE OBJECT-11 BUS ERROR (R2): on the ST the 5th button's store at `$ff1100` is in the unmapped band below the I/O page
  — a bus error, where the oracle silently drops it (PLAUSIBLE for the iron; the oracle's side measured).

RESOLVED DEBT: the store above RAM, a host-only class every bus accessor now refuses by name; the stale chip seeds and
register files across bench runs; the hand-written interrupted-case list (derived by construction now).

**aes — band 3 wave 3: one DIVERGENCE (the pass that never ends, refused off target), what stays unpinned, what is
deferred, the survivors, and the ROM's findings.**

A DOCUMENTED DIVERGENCE: `fs_input` with a directory to read and its working path EMPTY. The ROM never returns: no
directory is read, so fm_do is never called, and the selection field is redrawn for ever (the whole memory, stack
included, is the same at consecutive arrivals at the pass's head, 6,810 instructions apart). There are two roads to it:
- the caller's path is empty — `fs_input("")`;
- the close box over a path whose only `\` is its first byte (`\*.*`), after a formatted text left a `:` or a `\` in
  AES_FMTSTR's last bytes: the copy fs_back's downward scan aims lands its NUL on the path's first byte.
The TARGET build does the same as the ROM. The HOST build refuses the run by name on its first such pass
(`refuse_a_pass_that_never_ends`); the condition is exactly the ROM's fixed point — the read flag set and
streq(path last read, working path), which at a loop top with the flag set is true only for an empty working path — so
it cannot refuse a pass the ROM would leave. Pinned against the ROM's memory at that pass for both roads; the second
road's machine is DERIVED (the ROM's own ob_draw of an application's one-object dialog, an FTEXT whose template is 77
characters ending in `:`, or has `\` as its 78th).

UNPINNED, each with its reason:
- **Object 7's arm and `object > 22`.** Unreachable by real data: the slider box's three children tile it exactly, so
  ob_find never answers 7 (same code as 6 anyway), and fm_do answers nothing above 22 (objects 23 / 24 have flags 0 /
  LASTOB). The tiling is PROVED over the low-resolution snapshot's pixels; the raw resource's character units, which
  make it true in every resolution, were read by the review and are not pinned.
- **Between two waits** a session is held at its VDI calls — the calls themselves (opcode, intin, ptsin) and the
  selector's own memory at each (its tree, texts, scratches, the two paths). Not held there: any other byte, and
  contrl[5..10] / the MFDBs of a call (the leaves' exposure — bb_screen's — not fs_input's). The screen is held at the
  20 waits and at the end; on the target build at every slice mark.
- **Sessions run over GEMDOS REPLAYED**: a child binds no staged disk, and the bench cannot run real GEMDOS. Real
  GEMDOS on the C's side is the ten in-process runs. The 20 waiting sessions have no second differential (a run that
  blocks is not benched). A session that reads a hundred-name directory twice is past the replay's 128 calls.
- **The spin's second road** is pinned for two shapes of stale text; where fs_back's downward scan stops for `\*.*`
  otherwise depends on what was formatted last and on which ORECTs are free, and is pinned for the snapshot's state
  only (849 bytes down, at `$b549`).
- **A path of 80 characters or more** (finding 17 below): by reading, not run.
- **fs_format's two fs_sset answers** land in its own frame, which nothing reads; **the frame length of dos_snext's
  trap** cannot be seen on the host (the words above the function word are the caller's stack; 16 cycles on target,
  inside the pin tolerance); **the DTA global's re-read** in fs_active (nothing the loop stores can reach `$c838`).
- **`snext-function`** (Fsnext's function word made Fsfirst's) is KILLED on its targeted run, by the replay's ledger;
  its full run is ABNORMAL — the host's Fsfirst spins over real GEMDOS until the watchdog — and was not repeated.
- **fs_newdir past thirty-four full-length names** is over the bench cap (a hundred run 274,097 over the replay):
  Tier 1 only, the read and the sort priced by fs_active's own rows. A SHUFFLED hundred of full-length names is past
  the cap for fs_active too (sixty and eighty measure 0.816 / 0.815, a hundred reversed 0.818).
- **Low resolution only** (the snapshot's), fs_start included. Every session and every case over fs_input's machines
  runs UNPOISONED (the door's and GEMDOS's reasons: savptr and the pool's chain heads). Drive B: is the same staged
  disk answered for device 1 — it exercises the path, not a second medium.
- **The partition cuts at door calls and at registered slice ends, not at every trap arrival** (FP's decision). At
  trap granularity the rule as written cannot hold: 158 ROM instructions between Fsfirst and the first Fsnext are 0.90
  inside a read priced 0.84, and 1,264 between two of fm_do's VDI calls are 0.85 inside a key priced 0.77. A
  1,000-instruction grain was built and dropped. So a trap arrival is still matched by ordinal and memory only, and
  cost that crosses one is seen in the stretch beside it, not at the trap.
- **A sliced row cannot be `psg_seed` / `schedule` / `regs` seeded** (inherited from the interrupted rows).

DEFERRED, each measured:
- **The suite's margin under 200 s is thin**: `make test` quiet is 191–195 s (HEAD 140 s, the wave before its fix
  397 s), CPU-bound on ten workers. Three levers FP measured and did NOT take, each changing something to rule on:
  a CONTENT-KEYED DISK CACHE of the ROM-only derivations (the bench run would warm it; about 10 CPU-s per process);
  REUSING THE REAL-DISK RUN'S DELIVERIES for the replay run (one whole-session run fewer per session test; one
  argument in `_register_rows`); a LIGHTER SECOND DIFFERENTIAL for unregistered session rows, without tier3's own
  watched ROM run (it drops (EV)'s window vets there).
- **Registry import is still 22.9 CPU-s per process against HEAD's 13.4** (at the same load). What remains is the
  derivations themselves: six priced sessions at four whole-session ROM runs each, 686 GEMDOS re-enactments, about 820
  short ROM runs. Lazy rows would need lazy `pokes` through `case.verified_row` and tier3's `_row`; not attempted.
  `bench/tier3.py --out` is 103–118 CPU-s against HEAD's 89.4.
- **`vdi_helpers`' recording trap handler is not merged** into `aes_shell.Table` (the scripted trap and the replay
  are): one fixed entry shape and no script — not a trivial merge.
- **Left from the review's convention list** (R4 §9): DONE by the gate fix (the wave log's GATE entry) but for one —
  the tiling test still reads low-resolution pixels (above). FS_EMPTY_ROW is now spelt as what it is, FS_FILE_MARK (a
  row past the names is a file's row with no name: its kind byte alone, which is why a click on it is a file's);
  STRING_SPACE stays its own name (a character of the title's text, no row's kind).
- **A mark keeps the whole sixteen-megabyte image** (`aes_event.Marks.arrived`), where a GEMDOS call's and a pass's
  memory are kept as their megabyte of RAM (`aes_fslib.ram_in`): a session of eleven slices holds about a dozen images
  a shore while its rows are cut (about 1 GB peak in the worker that prices it, measured). Not taken: the marks are
  compared over the bench's diff spans, which would have to be shown to lie inside RAM first.
- **`rom_entered` takes no `budget`** (the reference path of `deliveries`): no caller needs one — a session too long
  for the default's margin cannot be stopped at an entry through it.
- **The seventh whole-session ROM run** of a file-selector session (`rom_vdi_calls`, over the same replayed machine as
  the replay's own watched run): 0.17–0.26 CPU-s a session, about 16 s summed over 80. Not merged.
- **Watch item** (R4): the bench blob grew 153,968 → 159,692 B; 34.7 KB remain below `staging_base`, about six waves
  of this size. `RomBench._vet_tenancy` refuses the overlap by name.

EQUIVALENT (or unreachable, or unobservable) SURVIVORS:
- fslib.c's event-free half + the glue: act-kind-not-reread (the kind is re-read from the DTA byte just stored; they
  differ only for a DTA above RAM, which the host refuses), act-bell-first (a local set before or after the call),
  el-stores-swapped (two words of one object), fmt-no-min (`row < min(9, n)` is `row < n` for nine rows) — EQUIVALENT;
  act-dta-not-reread and fmt-kind-first — EQUIVALENT ON EVERY REACHABLE MACHINE (the second differs only for a name of
  72 bytes or more, which no directory gives); fmt-answers-swapped and snext-with-a-word — UNOBSERVABLE (above).
- fs_input: show-tree-before-allocs (it masks the AES's own tree pointer, which has no top byte), pass-length-unsigned
  (a string length under the field's room), drag-zero-is-down (zero rows scroll nothing), row-old-put-down-when-none
  (fs_sel(0, …) is "no row"), row-reselected-when-same (ob_change to the state an object has draws nothing) —
  EQUIVALENT; read-any-put-down — EQUIVALENT ON EVERY STAGED MACHINE (every object but OK and Cancel that can end
  fm_do has state 0 when the read begins); row-buttons-are-rows — UNREACHABLE (the bound matters only past 22).
- K: s19 (the mark taken before the delivery is laid: both shores mark in the same order). FP:
  z-isr-inputs-staged-in-place (every caller hands `_interrupt_over` a throwaway image).

ROM FINDINGS (reproduced byte for byte unless marked):
1. fs_newdir builds the title with NO BOUND. `$9afe` has 40 bytes before gl_mntree (`$9b26`): `" " + spec + " "` fits a
   37-character spec; from 40 the menu tree's pointer is text, from 50 gl_rzero (`$9b30`) too. An application's
   fsel_input path is enough. Five cases.
2. The bell rings for a directory of EXACTLY 100 names: at the 100th name kept, one more Fsnext, its answer
   discarded, then Cconout(7), whether or not anything was cut. The hundred is of names KEPT (101 files under a spec
   that keeps eleven ring nothing).
3. fs_back cuts a long path: the `\` it inserts after a `:` goes through ins_char with a room of 64, so a tail of 63
   or more bytes is cut by a NUL instead of moved.
4. fs_pspec's default is always drive A (`"A:\*.*"`, whatever the current drive).
5. fs_active overwrites the DTA's file length (its low byte is where the kind is stored). Harmless: nothing reads it.
   A folder is a folder by its SUBDIR bit alone — read-only or archived, whatever the spec.
6. fs_format's half-box floor is dead for any real directory (it binds only above 100 names; pinned by a count of 200).
7. dos_snext's "found" is the answer's low WORD: a negative long with a zero low word is found AND sets DOS_ERR.
8. `fs_input("")` never returns — the divergence above.
9. A path edited, then Return or OK: the directory is READ, then the selector closes answering CANCEL (the read block
   puts OK down and does not clear the object in D7, so the switch still ends the loop and inf_what finds neither
   button). With a row selected before the edit, the row's name is handed back all the same.
10. The close box over `\*.*` writes BELOW the path's buffer: fs_back is called from one byte below the path and
    scans DOWN to the first `:` or `\`, inserts a `\` after it and copies `\*.*` over that — five bytes of AES data.
    Under the path lie the AES's four 81-byte text buffers (AES_RAWSTR `$b756`, AES_TMPLT `$b7a7`, the editor's
    `$b7f8`, AES_FMTSTR `$b849`), then the ORECT pool (`$b396..$b755`); in the staged machine the scan stops 849 bytes
    down, at `$b549`, the low byte of free ORECT 36's link (`$0000b53a`). (The review read that address as a linked
    table's node; it is not.)
11. The close box uses a STALE LENGTH: with the path typed as one letter, fs_pspec has already rewritten it to
    `A:\*.*` but the length is the typed one — fs_back starts on the `:` and inserts a second `\`; `A:\\*.*` lists
    nothing.
12. The user's spec is lost by the title (the directory is read twice, the second time with `*.*`) and by walking
    into a folder. GEMDOS is always searched with `*.*`; the spec is wildcmp's alone, which is why folders ignore it.
13. A key typed ahead is LOST at a hundred names (real GEMDOS): the bell is GEMDOS's Cconout, which polls the console
    and takes the key out of the BIOS ring into its own type-ahead buffer. The ROM returns over 99 names and blocks
    over 100.
14. Smaller: `gsx_sclip(gl_rfs)` at `$fe7e9e` is dead (fm_dial sets the whole screen first); an empty row is a file
    (clicked: the selection cleared; double-clicked: OK with no name); rows are left SELECTED in the tree when the
    selector closes; object 7's table row is unreachable and the table's upper bound dead above 22; Cancel hands back
    both strings as edited; a TOUCHEXIT object held repeats with no new event; the first draw is depth 1; a TOUCHEXIT
    click ends fm_do, and its release must arrive with the next event (alone it is nothing the wait asks for).
15. A SECOND ROAD TO THE SPIN (derived, pinned): AES_FMTSTR ends where the path begins and holds whatever FTEXT /
    FBOXTEXT ob_format merged last (G_TEXT does not pass through it); the selector's own fields are short and
    overwrite only its head. After a formatted text whose template runs 77 characters and ends in `:`, or has a `\`
    as its 78th, the close box over `\*.*` lands the copy's NUL on the path's first byte.
16. A spec past about 25 characters makes the FIRST ROW A FOLDER: the title has 28 bytes of text and the bytes after
    them are row 12's, so the row's kind byte is a character of the spec, and every kind but a space is a folder's
    (`$fe80d8 cmpi.b #32`). Clicking it puts the row's text, unformatted, into the path: `A:\MIXED\ABCDEFGH…*.*` and
    the first row clicked hand back `A:\MIXED\DEFGHABC.DEFGH*.* \ABCDEFGH…*.*`.
17. The path field's text is 80 bytes (`$d728..$d777`) and fs_sset copies with no bound: a path of 80 characters or
    more runs on over the selection field's text (`$d778`). BY READING — not run.
18. COST, not behaviour, found and fixed: the close box's two fs_back scans as GCC inlined them into fs_input (94 and
    114 cycles a byte against the ROM's 64; the arm alone 1.20) — the C now calls fs_back there as the ROM does
    (78 cycles a byte; 0.96). Left as it is: the last 8 cycles a byte would take `noclone`, which the host's clang
    does not know.

**aes — band 4 wave 0: three NAMED REFUSALS (calls the ROM does not survive), the staged-application class and its
limits, what stays unpinned, what is deferred, and the ROM's findings.**

NAMED DIVERGENCES — three calls HALT BY NAME ON BOTH BUILDS, each exactly where the ROM stops being a machine anything
can be held to, and each after the ROM's own stores:
- **doq: a read of more bytes than the pipe holds.** The ROM moves 64 KB of its own RAM down over itself, its Line-F
  handler's RAM copy (`$cc0e`) with it. On a read of 32, 40 or 48 bytes it RETURNS, through the moved handler
  (196,7xx instructions), over a destroyed AES — its caller's registers and SR not restored, every later Line-F call
  broken; on a read of 20 it returns over a rewritten vector page; on every other count tried it never returns
  (finding 5). The refusal is kept for EVERY count, and why: without the halt the host C's image equals the ROM's but
  for ONE WORD per shape — the moved handler's self-modifying store of its `movem` mask, 68000 code executed from the
  wrong offset of Line-F machinery this band does not reconstruct (ruling `$cc44`) — and the register file the caller
  gets back is the broken handler's. On target a real program sees no useful difference: the AES is dead either way.
- **aqueue: a pipe of a process id no PD has** (id 2 before anything was started, or `$100`): the ROM takes the vector
  page for a PD and never returns (finding 6).
- **ap_find: a name of twelve characters or more**, exactly where the ROM stops returning. Eleven are SERVED on both
  builds, on the premise that the caller's frame lies below 64 KB — true of the three static processes; an accessory's
  caller is unpinned (finding 10).
Not divergences of this wave's C, though the authors' reports listed them:
- psetup's `$8998` is not stored by the HOST C (dropped by name, `aes_event.SR_PSETUP_DROP`: it is the caller's SR,
  CCR and all); on target it holds OUR caller's SR, and the `.S` rows compare the word.
- getpd with no PD left is not a refusal of `pdpipe.c`: it is the bus accessor's standing "store at or above the top
  of RAM" — on target the C follows the ROM (finding 11).

THE STAGED-APPLICATION CLASS (ruling Q2) — what it is allowed to be, and where it may not be cited. A third process
made by the ROM's own pstart over a stub of exactly three instructions (a push of one immediate, ONE Line-F call of a
routine `aes_pdpipe.ALLOWED_CALLS` names, `jmp (SENTINEL).w`), vetted where it is made and as it lies in the machine
where it is entered; the process is the scheduler's, its PROGRAM is staged. It is TIER 1 ONLY: no row of
`case.ROW_REGISTRIES` or `transcription.TRANSCRIPTIONS` runs over one, every case over one carries the label, and
nothing learnt on one is quoted as what a real third process (an accessory) does. What stands on it this wave, each
said so in its row: fpdnm's and ap_find's third PD; psetup's second frame; pd_match's ninth name character on the
CDA's top byte; getpd with no PD left; aqueue's two waiters on one list and a third process's reader; takeoff's two
delays; signal woken between two others; the LIFO finding (finding 9). Its limits: one call per stub, so never more
than ten of the fifteen EVBs in use, never a refusal of tak_flag with a process already queued this wave, never an
EVB in the MIDDLE of three on a doubly linked list.

UNPINNED, each with its reason:
- **The composed path twin → dsptch → the refusing hook**, and the shadow of an entry that blocks: no twin calls
  dsptch yet (tak_flag is a leaf). RED proof 4 shows the hook stores nothing; it holds no C to the ROM at dsptch.
  Wave 1.
- **tak_flag**: a REFUSAL with a process already queued on the semaphore (a third process: wave 1's amutex battery);
  rlr's second load for the owner's store and the owner stored only when free (equivalent); a transient scribble of
  the count, set and put back inside the call (no at-return compare can see it). It has no REGISTERED Line-F row
  (two Tier 1 cases run its call word).
- **get_evb's EMPTY free list** (`$fe4012 beq`): fifteen EVBs, and three processes hold at most ten. Band 5's
  accessories.
- **acancel's NOCANCEL bit alone** (`$fe42a2 btst #0`): flag 1 never survives the call that sets it on a machine
  acancel is called over (finding 8 says where it IS read).
- **signal's `pd == rlr` return**: reached, redundant on every machine (the running process is never parked).
- **"Every read is where the ROM makes it"** (`evasync.c`'s header) is pinned for ONE alias — evinsert's list laid
  over the EVB's own predecessor field. Four other re-reads are unpinned, each a mutant that reads once and survives,
  each needing an EVB that lies over a list head or over itself, which only a fabricated alias would show:
  leave_list's two links, azombie's `$c84a`, get_evb's free-list head, evinsert's second and third stores.
- **No EVB is ever the MIDDLE of three** on a doubly linked list in any ROM-made machine of this wave (takeoff's and
  evremove's "predecessor is an EVB and successor too"): first and last only — a middle delay needs a fourth process.
- **fpdnm's accessory loop and getpd's accessory arm with a real PD** (`$c6b2[]`, `$c682`): the loader's, band 5.
- **ap_find's premise above 64 KB** (an accessory's caller): band 5.
- **aqueue's room computed as a WORD** (`move.w #128,d0 / sub.w`): it parts from a wider subtraction only for an
  index below -32,640, which only two negative-count writes reach — and the second's copy then runs FORWARD over
  48 KB of low RAM.
- **Three re-reads in the pipes' C**: the EVB's link read three times in aqueue's unlink, getpd's counters read again
  after the id's store, psetup's UDA pointer loaded once — no store between the reads reaches the word read on any
  machine made (each a surviving mutant, argued).
- **psetup / pstart have no REGISTERED through-Line-F row** (`aes.register`'s unpriced rows carry no drop for
  `$8998`); both run through their call word in the battery.
- **`pdpipe.S` is not mutation-swept**: a byte pin, 5 `.S` rows, `test_transcribed`.
- **The steered cases run the attribution pass NARROWED to their reasons** (`aes.run_function`'s `steered=`): the
  words a reason names are never inverted, so a store THROUGH or OF one of those words that the C skipped is not
  shown by the pass — a link, a pipe's index, a saved stack pointer, the PD counts; what holds those stores is the
  machines (each store changes what a list or a pipe holds) and the strict mutation sweep. Whether each reason is
  NEEDED is a sweep on demand (`AES_STEERED_FOR_NOTHING`), not a test of every run.
- **An odd index on a priced row**: the three shores agree on finding 7's one access, but no registered row has an
  odd index. The kit's odd-access vet is one-sided (it passes a build with FEWER odd accesses than the ROM); the case
  holds the equality itself. A kit matter, not touched (ruling Q7).
- **`EntryStops` cannot see two things** (its docstring says when an entry is watched again): a recursive entry's
  inner arrival, and a second process's call of an entry whose first caller parked inside it, before any other stop.
  A scenario's DECLARED arrivals are what holds a watched run to what it saw.
- **Coverage after the fix pass** was not re-measured (the wave log quotes the authors' builds).

DEFERRED, each measured or named:
- **THE SUITE'S 200 s LINE IS NOT HELD.** Quiet `make test`: HEAD 193–197 s, the tree 196.8–202.4 s over seven
  runs, mean 200.0, and 201.34 / 201.72 s after the gate's fixes (about a second for the forks at every call and the
  steered cases' narrowed pass). Levers taken are in the wave log. NOT taken:
  - band 3 wave 3's "reuse the real-disk run's deliveries for the replay" (STILL untaken: every edit is in the file
    selector's batteries, and its content-neutrality — the same deliveries on both machines — is unmeasured);
  - tak_flag leaving `SHADOWED` now that its flip has stood (measured over the eight lock / form / selector
    batteries, 1,346 tests, alternating: 91.3 / 86.9 s shadowed, 90.3 / 86.1 s unshadowed — under 1 s of wall, 4–13
    CPU-s; it needs the shadow's own tests to set the set themselves). tak_flag is STILL SHADOWED;
  - the time that would move the line is pre-existing: `test_aes_fs_input` ≈ 340 s summed, `test_tier3` ≈ 200 s,
    `test_boot_snapshot` ≈ 100 s.
- **The fork guard serves only a core that reaches no hook** (the eight list routines, the nine of the PDs and the
  pipes, tak_flag): a door user's guard is still a fresh interpreter with its hooks bound, ONCE before its
  differential and over the plain image only (the door's cases run no attribution pass).
- **A runtime guard for a nested arrival is NOT built** (a wave-1 prerequisite, **Next**): a twin that reaches another
  entry's wrapper is caught at the BUILD (the host build's own call graph: no function a twin reaches may refer to
  the door's hooks, in any file), not at the call.
- **THE KIT'S WATCH LOOP SPINS FOR EVER on a watch that arms the PC it is stopped at** (`recreate_kit/rom_bench.py`'s
  `watched`: no instruction runs between two stops, so its budget is never spent — measured, 1.2 M stops in 8 s; only
  the 300 s watchdog ends it). NOT fixed here (ruling Q7: no kit change in band 4): `aes_event.EntryStops` refuses,
  by name, to answer such a set, which makes it impossible from this project's watches. THE KIT FIX — refuse a
  resume that ran no instruction — is ITS OWN FUTURE KIT COMMIT, with the kit's suite and the six other projects'.
- **A row's companion and the registry's own sweeps run their C unguarded** (`aes.undropped`, `test_boot_snapshot`,
  `test_tier3`): the child-first guard is the batteries' run doors'. Pre-existing for every row.
- **`EV_BLOCK_KEYBOARD`, `AP_RDWR_READ` and a MOBLK's `LEAVE` / `ENTER`** stay named constants of the test helpers
  (each with its ROM citation), not header names: no C reads them yet.
- **Row registration at import stays** in the lists' battery (each of its rows is an arrival's machine: ten scenarios
  run in every process, 0.33 s): a mutant of the watch reddens there as a collection error. A lazy registry would be a
  kit-wide change.
- **`onto_the_woken_list` is a MACRO** (`aes/evasync.h`, shared by signal and pstart): as a `static inline` GCC swaps
  one compare's operands in aes_signal — the same cycles, not the same bytes.
- **`test_aes_fmlib.py`'s `machine()` lays `aes.leaf_machine` over a scheduler-made machine** (fq / dq's cases and
  six registered rows): the lever's guard over a running process — inert there (neither reaches dsptch), but a poked
  mix. Pre-existing, outside this wave; no case lays PD0 over ANOTHER running process (5,087 tests logged).
- **Small leftovers**: two private copies of `WORD_MASK` in batteries of other components; `evsync.h` / `switch.h`
  carry no `__ASSEMBLER__` guard (no `.S` includes them); `aes_dsptch_entered` is a host-only symbol that exists so
  the dispatch hook can be pinned before any twin calls dsptch, and goes when one does; the (EV) label is static (a
  row that now reaches only a rebound entry is still labelled through the door until its function's last ROM call is
  gone); `aes_spl7_save` / `aes_spl_restore` have no user yet.
- **Watch item**: the bench blob was 161,940 B at the review (159,488 at HEAD), 32,388 B below `staging_base`; the
  staging band of `aes_pdpipe` then grew `$100` → `$240` in the fix pass, no existing address moved.

EQUIVALENT (or unreachable, or unobservable) SURVIVORS:
- the lists (15): elinkoff read as the constant 4 (the RAM long is 4 from gem_main on), signal's rlr test, signal's
  mask read after its store, `$c84e` compared unsigned — EQUIVALENT; acancel clearing PD_EVFLG too — EQUIVALENT ON
  EVERY REACHABLE MACHINE (only signal sets a bit there, for a completed EVB, which acancel keeps); get_evb's empty
  list and NOCANCEL alone — UNREACHABLE; the four re-reads above — ALIAS-ONLY; four of the review's that are no-ops
  by construction.
- the twin and the protocol (3): the two equivalents and the transient scribble above. The Python machinery (2): the
  shadow's one-compare pass never taken, and its expected image laying every write — each falls through to the
  address-by-address compare with the same verdict (the pass is an optimisation, 63 % of a shadow's cost).
- the pipes (12): streq's operands swapped, doq's shift done for an index of 0, the other end's list read before the
  caller's own azombie, ap_find's fpdnm handed the caller's name — EQUIVALENT; four of the accessories' arm; the three
  re-reads and the word-wide room above.

ROM FINDINGS (reproduced byte for byte unless marked; each as the reviews and the fix pass corrected it):
1. **`$c84a` is the COMPLETED list — GEM's zombie list — not a timer list.** azombie pushes on it
   (`$fe3fc6..$fe3ff0`), apret searches it by address (`$fe41f0..$fe4202`). The delays wait on `$9c1a` (adelay
   `$fe55a8`, tchange `$fe4e0e`). `aes/aes.h` named it `AES_TIMER_LIST`; it is `AES_ZOMBIE_LIST` now.
2. **`$c84e` (gl_bpend), RE-DERIVED — the first report's "it never returns to 0, a cancelled multi-click wait leaks
   one" is RETRACTED as stated.** Every reference in the GEM text: +1 in abutton for a wait of more than one click
   (`$fe5648`); -1 while above 1 in evremove (`$fe5150`) AND in ctlmgr, the screen manager's own loop, after its
   evnt_multi — once if its button event came (`$fe4a36`), once if its mouse rectangle did (`$fe4a54`), though its
   own wait asked for one click; cleared by sh_main when deskmain returns (`$feb1e2`), the one place it goes back to
   0; read by b_click alone (`$fe4f72`), zero or not. So while the desktop runs it is never 0 once a multi-click
   wait has been queued (the desktop queues one in its first evnt_multi: the snapshot holds 1), and b_click opens
   the click delay on every press — the desktop's normal state, not a leak. A CANCELLED multi-click wait does leave
   its +1 behind (measured: "every event waited for, the timer comes" ends with 2 and none pending), but not for
   good: each wake of the screen manager by a press or by the mouse entering its rectangle takes one off, down to 1.
   BY READING beyond the two pinned evremove cases and that scenario.
3. **evremove takes ANY EVB's parameter for a click count** (`(e_parm >> 16) & $ff`): a button wait's clicks — and a
   MOUSE wait keeps its rectangle's x there. A mouse wait at x 150 woken while a double-click wait is pending counts
   `$c84e` down; at x 257 (low byte 1) it does not. Both pinned. NOT a delay's ticks (the first report's "or a
   delay's ticks from 131,072 up" was a misreading): a delay reaches evremove from tchange alone, which clears the
   parameter first (`$fe4e28 clr.l 16(a5)`).
4. **apret leaves the high word of ANY freed EVB's answer in `$c792`** (`$fe4266..$fe426e`), which ev_rets hands out
   as the buttons' state (`$fe6858`) — called at `$fe6ba8`, BEFORE ev_multi's first apret (`$fe6bce`): the word is
   STALE, the previous apret's, and after a mouse wait it is the rectangle's WIDTH. Pinned on apret's side;
   ev_multi's side is wave 2's.
5. **doq's read has no bound, and aqueue's read test is "any data", not "enough"**: a waiting reader of more than
   the pipe holds, or one process writing 8 bytes to itself and reading 16, takes the index negative, and doq's
   "move what is left" is lbcopy of that count unsigned — 64 KB of the AES's RAM moved down by the bytes read, the
   Line-F handler's RAM copy with it. MEASURED on the ROM (16 held unless said): a read of 32 returns in 196,732
   instructions, 40 in 196,729, 48 in 196,727 (32 held / 48 read: 196,775) — each landing on an instruction of the
   moved handler that still reaches `unlk; rts`; 20 returns in 259,961 over a rewritten vector page (45 odd
   accesses); 17, 18, 24, 33 of 32, 64, 80 of 64, 129 and 144 of 128, and 16 from an empty pipe never return
   (3,000,000 instructions). The first report's "never returns" was false for its own refusal case. REFUSED BY NAME
   (above).
6. **A pipe call for a process id no PD has** — id 2 before anything was started, or `$100` (a WORD compare: its low
   byte is the shell's id and finds nothing): fpdnm answers 0 and aqueue takes the vector page for the PD. Never
   returns (eight shapes, and through the trap door both ways). REFUSED BY NAME (above). Band 3's "a send to a pid
   with no PD spins", at its source.
7. **AN ODD INDEX after a one-byte write**: appl_write of ONE byte leaves the pipe's index odd, and the next write's
   `cmpi.w #20,(a3)` (`$fe5906`) reads the message's type at an odd address (`$ae97`) — a 68000 address error. The
   shores agree by name: the oracle (no address errors) runs on and its ledger names the one access; the host C
   halts by the accessors' name; the target build makes the same one odd access at the same address and equals the
   ROM's image and registers. No C change is right: on a 68000 both builds fault where the ROM faults. doq's merge
   walk makes another (`$fe591a`, a word at `$6907`) when a queued message's third word wraps its offset (`$7ff0`:
   the step is 16 + that word, AS A WORD).
8. **aqueue serves the first waiter at the other end UNCHECKED — a waiting WRITER overruns the pipe.** 32 bytes
   served after a read of 16 land past the pipe, on the next PD's first 16 bytes, the index reading 144 of 128;
   taken further (232 bytes) the ROM itself rewrites PD1's queue pointer and the spare PD's status and RETURNS. So
   "every PD's queue pointer names its own pipe" and "a spare PD's status is 0" are NOT invariants of the machine —
   pinned ROM-faithfully (C == ROM over the overrun), which is what tells the three spellings of "the pipe" and
   pstart's `clr.w p_stat` apart. And its `ori.w #1` (NOCANCEL) on the served EVB is NOT dead (the first report
   said it was): the served doq runs before azombie's `move.w #2`, and a waiting writer whose buffer is its own EVB
   writes the flag word, NOCANCEL set, into the pipe. A negative index is reachable and returned from too (a write
   of a negative count from a buffer below the pipe); aqueue's room and data tests are signed words.
9. **WAIT LISTS ARE LIFO**: evinsert queues at the HEAD and aqueue serves the head — seen on the mouse wait (a
   second rectangle's EVB found first) and, ON A STAGED APPLICATION ONLY, on a pipe (two writers parked, the last
   queued served first; the scoping saw the same on the lock, waiters [PD2, PD1] → owner PD2, over the same kind of
   stub). Where it concerns a third process it is a staged-application finding, not a claim about a real one.
10. **ap_find's frame is 10 bytes and lstcpy has no bound; the ROM's real boundary is TWELVE characters**, not eleven.
    The 11th lands on the top byte of aes_dispatch's saved A6 (off the 24-bit bus) and its NUL on bits 16..23 —
    already 0, because the trap handler runs the AES on the calling PD's UDA stack (`$fe3eee`) and the three static
    UDAs lie below 64 KB (measured: A6 = `$a1cc` at ap_find's entry; ten against eleven characters differ in ONE
    dead byte, `$a1a4`). `appl_find("CONTROL.ACC")` answers -1 on the ROM and on both builds; twelve never returns
    on the ROM and halts by name on both. THE BAND-5 CAVEAT: an accessory's UDA is the loader's; above 64 KB eleven
    characters zero a live byte of the caller's A6.
11. **getpd with no PD left** — the three static PDs handed out, no accessory loaded — **takes ADDRESS 0 for a PD**:
    id 3 stored at `$1c`, `$c682` counted to 1, uda_insuper's store aimed at ROM. (Shown on a staged application's
    machine; the kit refuses the ROM's own run, "store into the ROM window".)
12. **The spare PD is shadowed by PD0**: it is blank-named with id 0 until pstart numbers it, and PD0's name is eight
    blanks — so fpdnm by id 0 or by eight blanks finds PD0 first, and appl_find of eight blanks answers 0.
13. Smaller, each pinned unless said: azombie stores the WHOLE flag word (2), so a delay's 4, the mouse-leave 8 and
    NOCANCEL are gone once an EVB is completed; signal's two guards are dead on every reachable machine; iasync never
    tests get_evb's 0 (BY READING: it would store through address 0); a wait list's first EVB points back at the
    head "as an EVB" (head less the RAM long `$97f6` = 4); apret matches its mask by EQUALITY, acancel by AND;
    apret's unlink from its process's list stores 0 in every one of the ROM's own calls (ev_multi's aprets take the
    deepest EVB first — the non-zero store is a labelled case); tak_flag's refusal leaves the owner's HIGH word in
    D0 over a cleared low word, takes a free semaphore whatever owner the last release left, and never touches the
    wait list; pd_match compares against an 8-byte COPY ended in its own frame (a name matches only blank-padded to
    eight); doq writes through the PD's queue pointer and reads the message back at `pd + 56`, reads its count ONCE,
    and leaves a merged redraw's bytes in the pipe beyond the index; psetup parks its CALLER's SR in `$8998`; aqueue
    picks its list by `writing XOR ready` on WHOLE words (`$100` picks the writers').

**bios — the console's four BLITTER screen routines** (`$fc47be`, `$fc4852`, `$fc48b6`, `$fc4936`): TOS 1.02 installs
them on a machine with a blitter; the captured ST holds the CPU set, and each reconstruction halts on a vector that is
not it. Likewise a console of six or more bit planes — the ROM's own fill table at `$fd15ba` has three entries — and
`$fca914`, the console re-initialisation after a resolution change (still `Setscreen`'s halt; the font-geometry body it `bsr`s into at `$fc4a48` is the escape's v_fontinit, `$fc4a42`, transcribed in band 4).

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
is `bpl` against a `bcc` for the COLUMN: it would take a coordinate whose unclamped cell address is not in the machine's
megabyte even wrapped, so the reconstruction's own bound fires where the original walks its address space. The ROW's is driven
since band 4 (an ESC Y row byte below the bias, which the console now wraps on the 24-bit bus as the ROM does). And
the console's poison/attribution pass is OFF: the bytes the oracle writes ARE the driver's control state, so poison
would be indistinguishable from the routine's own output; `vt52.canary` stands in for the pixel cases.

**bios — the floppy VBL** (`$fc1bc4`, reached from `isr_vbl` past the `flock` gate) stays halted on the PSG's account:
it merges drive-select bits with a direct YM2149 read-modify-write, a path this project has no door for (see wave 5).

**gemdos — the dispatcher's arms are RECONSTRUCTED as of fs wave 3 band 4; what is not is everything behind the
termination record's longjmp.** The REDIRECTED arms (`$fd328a`), the DEVICE arm (`$fc99bc`) and the DEVICE-NAME arm
(`$fc9aca`) are verified, and the media-change recovery's two helpers `$fc93f4`/`$fc9468` are proved STANDALONE. What is
NOT: the E_CHG RECOVERY `$fc951e..$fc973a` (the drive's OFDs, the FAT OFD, node slots, DND tree and DMD freed, `Getbpb`,
`$fc53c0`, re-dispatch at `$fc94ee`) and the non-E_CHG error arm `$fc96e8` — both are reached through a `longjmp` over a
record the C core does not have, and a host longjmp cannot unwind through the ctypes frames of the handler hook. A future
caller of `gemdos_free_drive_ofds` must pass whatever A4 the innermost fs routine left, NOT the DMD, or it silently fixes the
ROM's bug. Two DIVERGENCES are recorded, not pinned: the redirected `Cconin` at EOF answers the stale `-14(a6)` byte (pinned
off target only; on target it is an uninitialised C local), and after an echoing redirected `Cconrs` the ROM's `$7ef4`
record points into a dead nested frame while the C leaves it untouched (the cases drop that span from the compare by name,
since VDI band 3 as a `case.run(dropped_windows=…)` window — a slice that never nests leaves it unwritten and compared — and the
Tier 3 row carries the same named mask). The
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

**gemdos — the PROCESS group's one modelling limit (it has no halts left).** `Fclose` of an open FILE is reconstructed
(fs wave 3 band 2), the dispatcher's character-device routing (band 4), and `Pexec` modes 0 and 3 LOAD (band 4:
`$fc6d14` looks the file up, `$fc85ea` loads and relocates it). The limit is the Mega ST battery
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
