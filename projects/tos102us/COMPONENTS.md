# COMPONENTS — the evidence-backed address map of TOS 1.02 (US)

`TOS102US.img`, 196,608 bytes, OS version `0x0102`, dated 1987-04-22, decoded at
**`0xFC0000`–`0xFEFFFF`** on the ST. Every address in this file is a real ROM/machine
address, and so is every address in `names.txt` and in `decomp.c` — the image is imported
raw at `0xFC0000` and has no relocation table, so a Ghidra address IS a ROM address.

**Every claim below carries the address it was read from.** Where a boundary could not be
established it says so instead of guessing; the open questions are collected at the end.

## How the numbers were produced

```bash
bash projects/tos102us/run.sh          # bootstrap: seeds -> Ghidra -> decomp.c
bash projects/tos102us/reapply.sh      # re-apply names.txt, re-export decomp.c
bash tools/hw_scan.sh projects/tos102us/ghidra_proj tos102us TOS102US.img \
     projects/tos102us/out/hw_scan.tsv 0xFF0000      # F/E/H records per function
m68k-elf-objdump -D -b binary -m 68000 --adjust-vma=0xfc0000 tools/hatari/TOS102US.img
```

State of the bootstrap at the time of writing: **1,292 functions**, 1,219 of them
decompiled (73 fail, see "Known gaps"); function bodies cover **137,555 of 196,608 bytes
(70.0%)**, leaving **59,053 bytes** outside any function — almost all of it the data blocks
listed below. `names.txt` applies with **zero failures** (272 `fn`, 174 `var`, 44 `cmt` —
`ApplyNames` counts only what it applied, so its log line equalling those three counts *is*
the check). Run `run.sh` and then `reapply.sh` before quoting the function count: the fresh
export writes its index before the decompiler has walked the image, and the decompiler itself
creates the last two functions (`0xFC9314`, `0xFC932A`) while it runs, so `run.sh` alone
reports 1,290.

Two structural facts decide how much of a TOS ROM a decompiler can see, and both are handled
by this project's loader (`tools/ghidra_scripts/RomLoader.java`, `LineFResolve.java`):

1. **Nothing calls anything.** Each layer is entered through a dispatch table, so a flow
   follower starting at the reset vector finds the boot chain and little else. The tables are
   parsed by `gen_seeds.py` and turned into **903 function seeds** applied before analysis.
   901 of them take (the two that do not are the AES arms noted under `aes`).
2. **GEM does not use `jsr`.** The AES and the desktop call their own routines with a
   one-word `$fXXX` Line-F opcode (below). Ghidra's 68000 has no constructor for that row, so
   before `LineFResolve` every GEM function truncated at its first call. It resolves
   **1,979 opcode words** in the bootstrap.

## ROM layout, in address order

| range | bytes | what | evidence |
|---|---:|---|---|
| `0xFC0000..0xFC002F` | 48 | OS header | `0xFC0000` = `bra.s` 0x2e; fields parsed below |
| `0xFC0030..0xFC066F` | 1,600 | **boot**: reset, cartridge probe, memory sizing, RAM test, vector table, hardware init | reset PC in the header at `+0x04` |
| `0xFC0670..0xFC0B4F` | 1,248 | **bios/xbios** trap entries, the shared dispatcher and the two tables | `0xFC07F2`/`0xFC07F8` installed into `$b8`/`$b4` at `0xFC0372`/`0xFC036A` |
| `0xFC0B50..0xFC4E5D` | 17,166 | **bios/xbios** implementation: bombs handler, screen, floppy + DMA, MFP/RS232/MIDI, IKBD/ACIA, console, RTC | dispatch-table targets span `0xFC0670..0xFC4698` |
| `0xFC4E5E..0xFC5215` | 952 | **gemdos/gem** trap installation and the GEMDOS entry glue | `0xFC4E5E` writes `$84`, `0xFC4E72` writes `$88` |
| `0xFC5216..0xFC9F0B` | 19,702 | **gemdos**: file system, handles, processes, memory, console, time (compiled C) | GEMDOS table targets span `0xFC5216..0xFC9EB2` |
| `0xFC9F0C..0xFD2F21` | 36,886 | **linea + vdi**: the Line-A handler and table, the rasterizers, the VDI dispatcher and its functions | Line-A vector `$28` := `0xFC9F0C` at `0xFC037A`; VDI table targets to `0xFD2E84` |
| `0xFD2F22..0xFD39F5` | 2,772 | **data**: VDI/Line-A switch and state tables | e.g. the 5-arm switch table at `0xFD3900` used by `0xFCABD0` |
| `0xFD39F6..0xFD5B85` | 8,592 | **data**: the three system fonts (6×6, 8×8, 8×16) | header chain parsed below; `0xFC9F8A` points at all three |
| `0xFD5B86..0xFD9EC9` | 17,220 | **data**: the AES resource, the desktop resource, the default `DESKTOP.INF` text, the FORMAT/DISKCOPY dialogs | `'GEMUSA.RSC'` `0xFD6F3E`, `'HDESKUSA.RSC'` `0xFD83BF`, `'#a000000'` `0xFD98CC`, `'FORMAT'` `0xFD9DEA` |
| `0xFD9ECA..0xFEE8FF` | 84,534 | **aes + desk** text (compiled C, Line-F calls) | `0xFD9ECA` is the GEM entry named by the MUPB |
| `0xFEE900..0xFEFFF3` | 5,876 | **aes/desk** data: the Line-F call table, compiler switch tables, strings | `0xFEE900` is read by the Line-F handler at `0xFEE8D6` |
| `0xFEFFF4..0xFEFFFF` | 12 | the GEM memory-usage parameter block | `os_magic` at `0xFC0014` points here |

## The OS header (`0xFC0000`, 48 bytes)

| offset | address | field | value |
|---|---|---|---|
| `+0x00` | `0xFC0000` | `bra.s` to the reset PC | `0x602E` |
| `+0x02` | `0xFC0002` | `os_version` | `0x0102` |
| `+0x04` | `0xFC0004` | `os_reset_pc` | `0x00FC0030` |
| `+0x08` | `0xFC0008` | `os_beg` | `0x00FC0000` |
| `+0x0c` | `0xFC000C` | `os_end` (first RAM byte above the OS BSS) | `0x00008900` |
| `+0x10` | `0xFC0010` | `os_rsv1` | `0x00FC0030` |
| `+0x14` | `0xFC0014` | `os_magic` → GEM MUPB | `0x00FEFFF4` |
| `+0x18` | `0xFC0018` | `os_date` (BCD mm-dd-yyyy) | `0x04221987` |
| `+0x1c` | `0xFC001C` | `os_conf` | `0x0000` |
| `+0x1e` | `0xFC001E` | `os_dosdate` | `0x0E96` (copied to `$8840` at `0xFC0460`) |
| `+0x20` | `0xFC0020` | `p_root` → GEMDOS memory-pool root in RAM | `0x00007E9C` |
| `+0x24` | `0xFC0024` | `pkbshift` → the keyboard shift-state byte | `0x00000E61` |
| `+0x28` | `0xFC0028` | `p_run` → the current basepage pointer | `0x000087CE` |
| `+0x2c` | `0xFC002C` | `p_rsv2` | `0` |

`p_root`, `pkbshift` and `p_run` are the three RAM addresses the header itself publishes, and
the dispatchers use them: the GEMDOS trap entry reads `p_run` at `0xFC4F8C`.

## The GEM memory-usage parameter block (`0xFEFFF4`)

Three longwords, the last 12 bytes of the ROM:

| offset | address | value | reading |
|---|---|---|---|
| `+0x00` | `0xFEFFF4` | `0x87654321` | the MUPB magic — this is what identifies the block |
| `+0x04` | `0xFEFFF8` | `0x0000CA00` | the top of GEM's RAM usage (51,712 bytes), i.e. where `_membot` ends up once GEM is resident |
| `+0x08` | `0xFEFFFC` | `0x00FD9ECA` | the GEM entry point in ROM |

The two readings are asymmetric in strength: `0x00FD9ECA` **is** a ROM address and the code
there is the AES init (it installs the Line-F vector at `0xFD9F56`), so "entry point" is
read off the image. `0x0000CA00` is inferred from its magnitude and from being a RAM
address above `os_end` — it is the value `RomLoader` uses for the top of the `GEMBSS`
block, and it is consistent with the GEM globals the code actually touches (the highest
seen is `0xC946`), but no instruction was found that reads the field.

## Dispatch tables — the entry points of every component

| layer | entry | table | entries | format |
|---|---|---|---|---|
| BIOS | `trap #13` → `0xFC07F8` | `0xFC0846` | 12 (`0x00..0x0b`) | count word `0x000c`, then longwords; **bit 31 set ⇒ the entry is a pointer to a RAM vector** |
| XBIOS | `trap #14` → `0xFC07F2` | `0xFC0878` | 65 (`0..64`) | count word `0x0041`, then longwords |
| GEMDOS | `trap #1` → `0xFC4F6E`, dispatcher `0xFC94E4` | `0xFD307A` | 88 (`0x00..0x57`) | **6-byte records**: handler longword + an argument-descriptor word the dispatcher reads at `+4` |
| VDI | `trap #2`, `d0=0x73` → `0xFC9F9E`, dispatcher `0xFCA9F6` | `0xFD372C` and `0xFD37C8` | 39 (opcodes 1..39) + 32 (100..131) | longwords, contiguous: `0xFD372C + 39*4 = 0xFD37C8` |
| AES | `trap #2`, `d0=0xC8/0xC9` → `0xFE3EA6` → `0xFE65AA`, dispatcher `0xFE5D9C` | `0xFEF834` | 116 (opcodes 10..125) | longwords, indexed by `opcode-10` at `0xFE64C8` |
| Line-A | `$28` → `0xFC9F0C` | `0xFC9F4A` | 16 (`$a000..$a00f`) | longwords; the table address is returned in `a2` by `$a000` |
| Line-F (GEM internal) | `$2c` → a RAM copy of `0xFEE8C2` | `0xFEE900` | 658 (`$f000..$fa44`) | longwords; index = `opcode & 0x0fff` used as a **byte** offset |

Two nested word-offset tables (`jmp <table>(pc,d0.w)` over signed 16-bit displacements):
`0xFC4298`, 20 entries, the VDI escape (opcode 5) sub-functions, bound by `cmp #19` at
`0xFC428C`; and `0xFC46B2`, 8 entries, XBIOS 21 `Cursconf`'s sub-functions, bound by
`cmp #7` at `0xFC46A2`.

**Why the selector→name mapping is trusted.** It is the published TOS ABI, and three
independent cross-checks came out exactly right: every GEMDOS selector the ABI leaves
undefined (`0x0c`, `0x0d`, `0x0f`, `0x14..0x18`, `0x1b..0x29`, `0x2e`, `0x32..0x35`, `0x37`,
`0x38`, `0x44`, `0x4d`, `0x50..0x55`) lands on the single stub at `0xFC933E` and every
defined one does not; the AES's gaps (16–18, 27–29, 36–39, 48–49, 57–69, 82–99, 109,
115–119) all land on `0xFE64A6`; the XBIOS's (1, 40–63) on `0xFC0670`. Six XBIOS bodies were
read to pin the numbering directly: `Physbase` `0xFC0A92` reads `$ffff8201/8203`, `Logbase`
`0xFC0AA6` reads `$44e`, `Getrez` `0xFC0AAC` reads `$ffff8260`, `Setscreen` `0xFC0AB8`
writes `$44e`, `Random` `0xFC1510` seeds from `$4ba`, `Vsync` `0xFC07D0` spins on `$466`.

**Two addresses carry two names each, and that is real, not a clash:** `0xFCB120` is both
VDI 122 `v_show_c` and Line-A `$a009`, and `0xFD02CA` is both VDI 111 `vsc_form` and Line-A
`$a00b`. `names.txt` names each for the Line-A primitive and records the VDI opcode in the
`cmt`.

## The Line-F call mechanism (the thing that makes GEM readable or not)

The AES and the desktop are compiled so that **a subroutine call is one word**. TOS Malloc's
100 bytes at AES init (`0xFD9F36`), copies the handler from `0xFEE8C2`, and points vector
`$2c` at it (`0xFD9F56`). The handler decodes the word it faulted on:

* **even** (`$f2b4`): a call. `target = *(long *)(0xFEE900 + (op & 0x0fff))`, return address =
  the word after the opcode (`0xFEE8D6`–`0xFEE8E0`). One word instead of six.
* **odd** (`$f001`): a return — `unlk a6; rts`, plus a `movem` restore whose mask is
  `(op & 0x0ffe) * 4`, patched into the instruction at `0xFEE8F8` (`0xFEE8E2`–`0xFEE8FE`).

The table ends at `0xFEF347`: entry 658 would be `0xFEF348`, which is the string
`"\DESKTOP.INF"` (read by code at `0xFDA444`). Every one of the 658 targets is a function
prologue, and 600 of them are distinct.

`LineFResolve.java` models a call site as a **no-op with a comment**, exactly as
`LineAResolve` does for Line-A. The consequence is measurable and is a trap for the naming
loop: the 52 "hardware accesses" the portability scan attributes to the GEM text
(`0x5c8f2ea0`, `0xdffc0000`, …) are **artifacts** — constant propagation through a site
whose register clobbers are not modelled.

### Where the hardware really is

The scan's 220 `H` records split **bios/xbios bodies 120, boot 31, bios/xbios entries 14,
aes + desk 52 (all artifacts, above), linea + vdi 2, data 1** — so real chip access is the
boot, the BIOS and the XBIOS *plus two VDI sites*, not the BIOS/XBIOS alone. (The `data` one
is `0xFD5B88` writing `0x37743D44`: a stray instruction decoded inside the font block, an
artifact like the GEM 52.)

And the scan under-counts by construction: it records an access at the instruction that
performs it, so a `lea <register>,a5` followed by `move.w d0,(a5)+` is invisible to it.
**TOS 1.02 carries blitter code** and drives it exactly that way — ten `lea` sites load a
blitter register into an address register (`0xFC47BE`, `0xFC4852`, `0xFC48B6`, `0xFC4936` in
the VDI escape / raster helpers, `0xFCA20A`, `0xFCA5CA`, `0xFCEE6A`, `0xFCF9BE`, `0xFCFCCC`,
`0xFD0674` in the Line-A rasterizers), which is consistent with XBIOS 64 `Blitmode`
(`0xFC0EF6`) being implemented. All ten, and the VDI's two palette accesses
(the write at `0xFD2E66` in `vs_color`, the read at `0xFD2F06` in `vq_color`), use the
**24-bit alias** `$00FFxxxx` of the
I/O page rather than `$FFFFxxxx`; `RomLoader` creates that block too, which is what makes
them resolve to a label (`names.txt`: `hw_blitter_*`, `hw_palette_alias`) instead of to
nothing.

## The a5 base register (the other thing that makes a component readable)

The BIOS and the XBIOS address every system variable and every hardware register **through
`a5`**, which their shared dispatcher zeroes for them: `suba.l a5,a5` at `0xFC082C`, one
instruction before `jsr (a0)`. So `202d 044e` at `0xFC0AA6` is `_v_bas_ad`, and `102d 8260`
at `0xFC0AAE` is `$FFFF8260` (a sign-extended 16-bit displacement off zero, wrapped to 32
bits). Ghidra has no way to know that, so before the pin those bodies decompiled as
`unaff_A5 + 0x44e` — an expression no `var` line can name — in **308** places.

`run.sh` therefore runs `SetRegisterValue.java a5 0 0xfc0688 0xfc4e5d` as a pre-script: the
ROM variant of the a4 pin the `.PRG` projects use (`docs/ghidra-pipeline.md`, "Small-model C").
`Logbase`, `Getrez`, `Setscreen`, `Drvmap` and the rest then read named system variables, and
**107** `unaff_A5` uses are left, none of them in the pinned range.

**The range is the whole point, and it is not the whole program.** a5 is a base register only
where the dispatcher or the routine itself has zeroed it; elsewhere it is live data, and a
wrong pin is worse than none because the decompiler resolves operands off it just as
confidently:

* **excluded below `0xFC0688`** — the boot uses a5 as a *return address* (`lea ret(pc),a5 /
  bra.w 0xFC0672` at `0xFC0122`, `0xFC0130`, `0xFC013E`; the helper ends `jmp (a5)` at
  `0xFC0686`), and as an FDC pointer (`lea $ffff8604,a5` at `0xFC058C`). `0xFC0688`
  (`memory_size_probe`) zeroes a5 itself, which is why the pin can start there rather than at
  the component boundary `0xFC0670`.
* **excluded above `0xFC4E5D`** — the VDI and the AES take a5 as an incoming pointer
  (`0xFD2580` and `0xFD261C` account for 74 of the remaining uses on their own; `0xFCC9A6`,
  `0xFE64BA` and `0xFE837A` are others), which is where all 107 remaining `unaff_A5` uses are.
* **inside the range**, the routines that use a5 as something else all load it first
  (`lea $00ff8a20,a5` at `0xFC4852`/`0xFC48B6`, `movea.l 132(a4),a5` at `0xFC484C`), so the
  entry-point value the pin sets is never read.

## Per component

Function counts are from the bootstrap DB (`out/hw_scan.tsv`, `F` records); "code" is the
bytes inside function bodies. The `link a6` count is the number of `0x4E56` words in the
range — the Alcyon C frame prologue, hence the authorship column (`docs/agent-playbook.md`,
"When the target is COMPILED C").

| component | range | bytes | fns | code | `link a6` | per fn | hw | authorship |
|---|---|---:|---:|---:|---:|---:|---:|---|
| os header | `0xFC0000..0xFC002F` | 48 | 1 | 2 | 0 | — | 0 | data |
| boot | `0xFC0030..0xFC066F` | 1,600 | 13 | 1,328 | 0 | 0.00 | 31 | hand asm |
| bios/xbios entries | `0xFC0670..0xFC0B4F` | 1,248 | 29 | 776 | 0 | 0.00 | 14 | hand asm |
| bios/xbios bodies | `0xFC0B50..0xFC4E5D` | 17,166 | 177 | 14,122 | 17 | 0.10 | 120 | hand asm, a few C leaves |
| gemdos glue | `0xFC4E5E..0xFC5215` | 952 | 19 | 952 | 10 | 0.53 | 0 | mixed |
| gemdos | `0xFC5216..0xFC9F0B` | 19,702 | 127 | 19,682 | 119 | 0.94 | 0 | **compiled C** |
| linea + vdi | `0xFC9F0C..0xFD2F21` | 36,886 | 199 | 25,336 | 91 | 0.46 | 2 | asm rasterizers + C glue |
| data | `0xFD2F22..0xFD9EC9` | 28,584 | 1 | 26 | 0 | — | 1 | data |
| aes + desk | `0xFD9ECA..0xFEE8FF` | 84,534 | 726 | 75,331 | 464 | 0.64 | 52 | **compiled C** |
| aes/desk data | `0xFEE900..0xFEFFFF` | 5,888 | 0 | 0 | 0 | — | 0 | data |

The `code` column sums to 137,555 = the scan's `P function_bytes`, and the `fns` column to
1,292 — the 2-byte `os_header` "function" at `0xFC0000` is the row that reconciles them.
The `hw` column is the scan's `H` records attributed to a function whose entry is in the range;
it totals 220, and it is read further down under "Where the hardware really is".

### boot — `0xFC0030..0xFC066F`, 13 functions

Entry is the reset PC `0xFC0030` (OS header `+0x04`). In order: `sr := 0x2700`, `RESET`,
then the **cartridge probe** — `cmpi.l #0xFA52235F,0xFA0000` at `0xFC0036`, jumping to
`0xFA0004` if a diagnostic cartridge is present. Memory sizing runs at `0xFC0060`–`0xFC0206`
(`memctrl` `$424` → `$ffff8001` at `0xFC0056` and `0xFC00F2`, the RAM test writing
`0x200008` at `0xFC00FE`), the boot palette is copied from `0xFC06A8` to `$ffff8240` at
`0xFC00C0`, and the video base is set at `0xFC00CA`.

**The boot chain does not use `bsr`.** It calls with `lea ret(pc),a6 / bra.w sub` and returns
with `jmp (a6)`; there are exactly 5 such sites (`0xFC0042`, `0xFC004C`, `0xFC00A6`,
`0xFC00E4`, `0xFC0400`). Ghidra follows the branch and never comes back, so those return
addresses are code no flow follower reaches — `gen_seeds.py` finds them by signature
(`0x4DFA` + a small positive displacement + `bra.w`/`jmp`) and seeds them, which is what
recovered the 1,420-byte hole this range had in the first bootstrap.

Vector-table construction, `0xFC0302`–`0xFC03B6`, is the boot's most useful output and the
provenance of most of the handler names in `names.txt`:

| site | vector(s) | value |
|---|---|---|
| `0xFC0334` | `$08..$FC` (62 vectors) | `0xFC0B50` with the vector number in the ignored top address byte (`+0x01000000` per step) |
| `0xFC0340` | `$14` divide by zero | `0xFC07CE` (`rte`) |
| `0xFC034C` | `$64..$7C` autovectors | `0xFC07CE` |
| `0xFC0356` | `$70` level 4 (VBL) | `0xFC06DE` |
| `0xFC035E` | `$68` level 2 (HBL) | `0xFC06C8` |
| `0xFC0366` | `$88` `trap #2` | `0xFC07CE`, replaced at `0xFC4E72` |
| `0xFC036A` | `$B4` `trap #13` | `0xFC07F8` |
| `0xFC0372` | `$B8` `trap #14` | `0xFC07F2` |
| `0xFC037A` | `$28` Line-A | `0xFC9F0C` |
| `0xFC0382` / `0xFC038E` | `$400` `etv_timer`, `$408` `etv_term` | `0xFC0670` (`rts`) |
| `0xFC0386` | `$404` `etv_critic` | `0xFC07EE` (`moveq #-1,d0; rts`) |
| `0xFC0396` | `$456` `_vblqueue` | `$4CE`, then 8 longwords cleared → `_vbl_list` |
| `0xFC03B0` | `$51E..$59D` | 32 longwords copied from `0xFC09AE` — the initial `xconstat`/`xconin`/`xcostat`/`xconout` tables |
| `0xFC043C` | `$46E` `swv_vec` | `0xFC0030` (a monitor change reboots) |

RAM the boot owns: the whole vector page `$0..$3FF`, the system variables it initialises
above, and `$380..$3CF` — the exception dump the bombs handler at `0xFC0B54` writes
(`proc_regs` `$384`, `proc_pc` `$3C4`, `proc_usp` `$3C8`, `proc_stk` `$3CC`).

### bios — `trap #13`, table `0xFC0846`, 12 entries

`0xFC07F8` loads `a0` with the table and falls into the shared dispatcher `0xFC07FC`, which
switches the register frame to `savptr` (`$4A2`), bounds-checks the selector against the
table's count word, and indexes longwords. **A negative entry is a pointer to a RAM vector**
(`0xFC0828`: `bpl` → `jsr (a0)`, else `movea.l (a0),a0`) — that is how `Rwabs`, `Getbpb` and
`Mediach` reach the installable disk driver:

| # | name | target |
|---|---|---|
| 0 | `Getmpb` | `0xFC0A46` |
| 1 | `Bconstat` | `0xFC0984` |
| 2 | `Bconin` | `0xFC098C` |
| 3 | `Bconout` | `0xFC099C` |
| 4 | `Rwabs` | **indirect** via `hdv_rw` `$476` |
| 5 | `Setexc` | `0xFC0A72` |
| 6 | `Tickcal` | `0xFC0A8A` |
| 7 | `Getbpb` | **indirect** via `hdv_bpb` `$472` |
| 8 | `Bcostat` | `0xFC0994` |
| 9 | `Mediach` | **indirect** via `hdv_mediach` `$47E` |
| 10 | `Drvmap` | `0xFC0A2E` |
| 11 | `Kbshift` | `0xFC0A34` |

The BIOS *entries* are 4 to 20 bytes each (`0xFC0984..0xFC0A8A`); the drivers they call live
in the `0xFC0B50..0xFC4E5D` block together with the XBIOS's. That block holds **120** of the
scan's 220 hardware accesses — 67 MFP (`$fffffa01` has 13 access sites, the most of any
register in the image, tied with the PSG's `$ffff8800`), 18 PSG, 16 DMA, 7 ACIA, 3 shifter,
8 Mega ST clock (`$fffffc21..$fffffc3b`) and 1 blitter. It is the largest share but not all
of it: see "Where the hardware really is" below.

RAM: the keyboard tables' three-longword `keytbl` struct at **`$0E62`** (unshifted, shifted,
CapsLock — written by `Bioskeys` at `0xFC305A`, returned by `Keytbl` at `0xFC3052`), the
shift-state byte at `$0E61` (the header's `pkbshift`), and the console state the VDI escape
shares (`$2994`, loaded at `0xFC427A` and `0xFC4698`).

### xbios — `trap #14`, table `0xFC0878`, 65 entries

`0xFC07F2` → the same dispatcher. Opcodes `0..64`; **1 (`Ssbrk`) and 40..63 are unimplemented
and point at the bare `rts` at `0xFC0670`**, which is also `etv_timer`'s and `etv_term`'s
default. Opcode 64 `Blitmode` (`0xFC0EF6`) is present, so this ROM knows the blitter. Targets
run from `0xFC0670` to `0xFC4698`; the three notable outliers into the console driver are
`Cursconf` (21, `0xFC4698`) and, from the VDI side, escape (5, `0xFC427A`), which is how the
alpha cursor is shared between the BIOS console and the VDI.

The floppy group sits together — `Floprd` `0xFC1782`, `Flopwr` `0xFC1858`, `Flopfmt`
`0xFC1916`, `Flopver` `0xFC1AE2` — as does the serial/MIDI group (`Midiws` `0xFC2030`,
`Mfpint` `0xFC2658`, `Iorec` `0xFC28F6`, `Rsconf` `0xFC290E`) and the sound/PSG group
(`Giaccess` `0xFC2EA4`, `Offgibit` `0xFC2F02`, `Ongibit` `0xFC2EDC`, `Dosound` `0xFC3074`).

### gemdos — `trap #1`, table `0xFD307A`, 88 records — compiled C

`0xFC4F6E` (installed into `$84` at `0xFC4E5E`) serves **`Super` (0x20) inline** — the two
`cmpi.w #32` at `0xFC4F76`/`0xFC4F80` — and otherwise builds the process register frame off
`p_run` (`$87CE`, read at `0xFC4F8C`), switches to the supervisor stack at `0x16CE`
(`0xFC4FB8`) and calls the C dispatcher `0xFC94E4`.

The dispatcher is textbook Alcyon C: `link a6,#-54`, the argument frame at `8(a6)`, a
selector above `0x57` returning `EINVFN` (`moveq #-32,d0` at `0xFC9504`), and the table index
computed as `selector * 6 + 0xFD307A` at `0xFC9742`. Each record is a **handler longword plus
an argument-descriptor word** which the dispatcher reads at `+4` and uses to decide the
handle-redirection path (`0xFC9754` onwards). The unimplemented stub is `0xFC933E`
(`link a6,#-4; moveq #-32,d0; unlk; rts`).

Authorship is unambiguous: 119 `link a6` frames for 127 functions, and **zero hardware
accesses in the whole range** — GEMDOS reaches the disk only through the BIOS.

RAM: `p_root` `$7E9C` and `p_run` `$87CE` (both published in the OS header), the supervisor
stack top `0x16CE`, and a call-depth counter at `$68FA` (`0xFC94E8`). THE THREE ADDRESSES THIS
PARAGRAPH ONCE CALLED A PROCESS TABLE ARE NOT ONE, and the file-system and process waves each
established what they really are: `0x8380` is the per-drive DMD table (`$8380 + drive * 4`),
`0x8066` is one reference count per DIRECTORY NODE, and `$87CC` is the DRIVE a failed BIOS disk
call came from — the reading below, from the ROM's own stores, rather than the guess here. The
full extent of the GEMDOS BSS was not established — but the MEMORY MANAGER's part of it now is
(see below).

**The memory manager's own RAM**, established by the recreate's GEMDOS memory group
(`recreate/src/gemdos/memory.c`, `recreate/include/gemdos/memory.h`):

| range | what | evidence |
|---|---|---|
| `$7E8E..$7E99` | GEMDOS's own **MPB** — `mp_mfl`, `mp_mal`, `mp_rover` | `Mfree` `0xFC8B04` reads `mp_mal` at `$7E92`; `Malloc` `0xFC8ACA` passes `$7E8E` to `md_alloc`; GEMDOS's init `0xFC935E` hands `$7E8E` to BIOS `Getmpb` |
| `$7E9C..` | **`p_root`** is an ARRAY, one free-chain head per record SIZE CLASS — not a single list head | `0xFC7F30`/`0xFC7FB6` index it as `p_root + (int16)class * 4`; class 1 is the 16-byte memory descriptor, class 16 the 256-byte basepage the init cuts at `0xFC9376`. `p_root[0..21]` are zero in the snapshot and other GEMDOS data starts at `$7EF4` |
| `$2A6E..$68ED` | the **record arena** every descriptor, basepage and file-system record is bump-allocated from | `0xFC7EFE` adds `$2A6E`; the init writes `move.w #8000,$8780` at `0xFC936E`, so 16,000 bytes |
| `$68F0` | words handed out so far (the bump cursor), two bytes above the arena's top | `0xFC7EF2`/`0xFC7F08` |
| `$8780` | ...and words remaining; `used + left == 8000` on the captured machine | `0xFC7EDC`/`0xFC7EEC` |

A **memory descriptor is not an array slot**: it is an 18-byte arena record (a class word, then
`m_link`/`m_start`/`m_length`/`m_own`), recycled through `p_root[1]`. That is where TOS 1.02's
"out of memory descriptors" comes from — `Malloc` refuses a SPLIT when the arena is spent, over
RAM that is plainly free, and `Mshrink` does not check at all and stores the remainder's fields
through a null pointer into the reset vectors. Both are reproduced rather than corrected
(`recreate/test/test_gemdos_memory_mshrink.py`).

The one descriptor that is NOT an arena record is `$048E`, the fixed quartet BIOS `Getmpb`
builds — it is on the captured machine's ALLOCATED list, because GEMDOS's init passed its own MPB
to `Getmpb` and then allocated out of it.

**The trap entry's own RAM, and THE PROCESS FRAME**, established by the recreate's GEMDOS
trap/dispatcher group (`recreate/src/gemdos/trap1.S`, `dispatch.c`, `leaves.c`). The entry does not
use a shared save area the way the BIOS dispatcher's `savptr` does — it frames the calling process
into ITS OWN BASEPAGE and onto the caller's own stack, because a GEMDOS call is the one a process
can be destroyed inside of:

| basepage offset | field | evidence |
|---|---|---|
| `+$20` | `p_dta` | `Fgetdta` `0xFC6CA4`, `Fsetdta` `0xFC6CB6` |
| `+$24` | `p_parent` | `Pterm` `0xFC805A` reassigns `p_run` from it |
| `+$30..$35` | `p_uft`, the six STANDARD HANDLES | `Fforce` `0xFC5328` writes one; the dispatcher's redirection reads one at `0xFC9794`/`0xFC9972` |
| `+$36`, `+$37` | `p_lddrv`, `p_curdrv` | `Dgetdrv` `0xFC6CEA`, `Dsetdrv` `0xFC6CCE` |
| `+$68..$77` | D0, A3, A4, A5 — saved before the entry has a stack to save them on | `0xFC4F92`; the epilogue's `movem.l $68(a5),d0/a3-a6` at `0xFC500E` restores five |
| `+$78` | A6, which had to be pushed first so it could become `p_run` | `0xFC4F98` |
| `+$7C` | -> the REST of the frame, 50 bytes on the caller's own stack: the other stack pointer, the SR, the return PC, then D1-D7/A0-A2 | `0xFC4FB4`/`0xFC4FD0`; `lea 50(a5),a0` at `0xFC4FBE` is both the frame's length and the way back up to the caller's argument words |

...so a GEMDOS call hands the caller back EVERY register (D0 is the result), where a BIOS call hands
back nine. `0xFC4FE8`, the epilogue, is a SECOND ENTRY POINT: `Pterm` `0xFC8076` reassigns `p_run`
to the parent, plants the exit code in the parent's `+$68`, and `jsr`s there, so the frame unwound
is the parent's and the `rte` resumes whoever called the parent's own GEMDOS call.

**The rest of GEMDOS's BSS that this group established**, which with the memory manager's block
above leaves little of `$68F0..$8840` unaccounted for:

| address | what | evidence |
|---|---|---|
| `$0EB0` | where `0xFC4EAC`'s trampoline parks its return address across a `trap #13` — GEMDOS reaches the BIOS this way, `Dsetdrv` `0xFC6CD6` included | `0xFC4EAC` |
| `$68FA` | the call-depth counter: CLEARED and then BUMPED, at a label the termination path branches back to | `0xFC94E8`, `0xFC94EE` |
| `$68FC` | the sub-second accumulator the 200 Hz tick rolls into the time word at 2,000 | `0xFC9CD8`, `0xFC9CDE` |
| `$75B0` | GEMDOS's own TIME word | `Tgettime` `0xFC9EA6`, `Tsettime` `0xFC9EF4`, the tick `0xFC9CF2` |
| `$7DEE` | the DIRECTORY NODE table — one longword per node, walked by the media-change arm and indexed by a basepage's `p_curdir` bytes (CORRECTED: the process wave read it as "one longword per process slot") | `0xFC95B2`, `0xFC51DE` |
| `$7EF4` | the process-termination record `0xFC4F38` arms — three longwords of the dispatcher's own 68000 frame. The FILE SYSTEM's critical-error abort is what longjmps to it (`0xFC5986` and four more), and `Pexec` saves a copy to `$7560` before arming its own; `Pterm` does NOT — it `jsr`s the trap entry's epilogue (CORRECTED: the process wave said `Pterm` longjmps here) | `0xFC950A`, `0xFC81C2` |
| `$8066` | one REFERENCE COUNT BYTE per directory node, bumped by `gemdos_inherit_curdir` and dropped by a process's release, both indexed by a `p_curdir` byte (CORRECTED: the process wave read it as "one flag byte per process slot") | `0xFC959E`, `0xFC51DE`, `0xFC80EA` |
| `$8092` | the HANDLE TABLE — 75 records of ten bytes, indexed from handle 6, whose `+0` longword POINTS AT a 64-byte OFD pool record (or, negative, names a character device); `+4` is the owning basepage and `+8` a reference count | `0xFC9950`, `0xFC51C0` |
| `$879C` | a longword the timer tick accumulates ticks into (role not established beyond that) | `0xFC9CCE` |
| `$8840` | GEMDOS's own DATE word, seeded from `os_dosdate` | `Tgetdate` `0xFC9E1E`, `Tsetdate` `0xFC9E8A`, `0xFC0460` |

**GEMDOS keeps its own clock and does not ask the hardware for it.** `0xFC9CC0` is hooked onto
`etv_timer` (the chain at `0xFC4EF6`, which tails into the saved vector at `$16D2`) and advances
`$879C`, `$68FC`, `$75B0` and the date — which is why `Tgetdate` and `Tgettime` are one RAM word
each, and why `Tsetdate`/`Tsettime` have to publish what they store BACK to the 6301 through XBIOS
`Settime` (`0xFC50B4`, a `trap #14`).

**The ARGUMENT-DESCRIPTOR word** at `+4` of each record does two jobs. Its low two bits are an
argument-frame CLASS — the dispatcher copies 4, 8, 12 or 14 bytes of the caller's words onto the
stack before the `jsr`, in four straight-line arms at `0xFC9BB6`, `0xFC9BD8`, `0xFC9C0A` and
`0xFC9C4E` — and bit 7 marks a call whose argument is a HANDLE. For the character-device group
(selectors 1..11 and 16..19, carved out by the four compares at `0xFC9762..0xFC9784`) the low seven
bits are a STANDARD HANDLE NUMBER: `$80`->0 stdin, `$81`->1 stdout, `$82`->2 stdaux, `$83`->3 stdprn.
The dispatcher looks that handle up in `p_uft` and either takes the 19-entry table at `0xFD328A`
(the handle has been `Fforce`d to a file, so `Cconin` becomes an `Fread`) or REWRITES the descriptor
to 1 for `Cconws`/`Cconrs` and 0 for the rest and calls the handler directly (`0xFC98FE`).

**THE FILE SYSTEM's data structures** (`0xFC5216..0xFC7CCE`), established by the recreate's GEMDOS
file-system group (`recreate/src/gemdos/fs_disk.c`, `fs_name.c`, `recreate/include/gemdos/fs.h`).
GEMDOS reaches a disk through exactly three BIOS calls — `Rwabs`, `Getbpb`, `Mediach` — all three
of them **indirect** through the RAM vectors `hdv_rw` `$476` / `hdv_bpb` `$472` / `hdv_mediach`
`$47E` (the table entries with bit 31 set, above). There is no fourth door: the "zero hardware
accesses in the whole range" above is the other half of this fact.

**ONE CLUSTER-NUMBERED ADDRESS SPACE, and it is the idea the whole layer rests on.** `0xFC53C0`
builds a *drive media descriptor* out of the BPB in which the FAT, the root directory and the data
area are all addressed as clusters of one space: data clusters are 2 upwards, the root directory
occupies the clusters just below 0, and the FAT the ones below those. Each region carries a BIAS
(`m_recoff[type]`) that turns a record of that space back into the record number `Rwabs` takes —
which is what lets one buffer cache hold FAT sectors, directory sectors and data sectors and tell
them apart by arithmetic on the record alone (`0xFC5A98`, three compares and a shift).

| record offset | built at | from |
|---|---|---|
| `m_recoff[0]` FAT | `0xFC5564` | `fatrec - (FAT pseudo-cluster) * clsiz` |
| `m_recoff[1]` root dir | `0xFC5580` | `fatrec + fsiz - (root pseudo-cluster) * clsiz` |
| `m_recoff[2]` data | `0xFC55A2` | `datrec - 2 * clsiz` |

**The BPB's `fatrec` names the SECOND FAT**, not the first, which is why `m_recoff[0]` is derived
from it and why a dirty FAT buffer is written TWICE — the second copy at its own record, the first
at `record - m_fsiz` (`0xFC59B2`). Only buffer type 0 gets that.

| structure | size | fields established |
|---|---|---|
| **BPB** (Getbpb's answer) | 18 | `recsiz` 0, `clsiz` 2, `clsizb` 4, `rdlen` 6, `fsiz` 8, `fatrec` 10, `datrec` 12, `numcl` 14, `bflags` 16 (bit 0 = 16-bit FAT) |
| **DMD** (per open drive, pool class 3) | 48 | `m_recoff[3]` 0/2/4, `m_drvnum` 6, `m_fsiz` 8, `m_clsiz` 10, `m_clsizb` 12, `m_recsiz` 14, `m_numcl` 16, then three log2/mask PAIRS at 18/20 (clsiz), 22/24 (recsiz) and 26 (clsizb) taken from the mask table at `0xFD2FC8` (`table[n] == (1 << n) - 1`), the FAT's pseudo-OFD at 28, the root DND at 36, and `bflags & 1` at 40 |
| **BCB** (one cached sector) | 20 | `b_link` 0, `b_bufdrv` 4 (`-1` = EMPTY), `b_buftyp` 6 (0 FAT / 1 root dir / 2 data), `b_bufrec` 8, `b_dirty` 10, `b_dm` 12, `b_bufr` 16 |
| **DND** (a directory node, pool class 4) | 64 | the 11 FCB name bytes at 0, `d_strtcl` 14, `d_ofd` 20, `d_drv` 36 |
| **OFD** (an open file, pool class 4) | 64 | `o_strtcl` 10, `o_fileln` 12, `o_dmd` 16 |
| **directory entry** | 32 | the 11 FCB name bytes at 0, the attribute at 11 (8 = volume label) |

`0xFC50FA` cuts the DMD and its three satellites out of the record pool in one go and files the DMD
at `$8380 + drive * 4`; `$8784` is a word bitmap of the drives whose DMD has been built, and
`0xFC67DE` is what builds one on first use.

**THE BUFFER CACHE** is two singly-linked BCB lists headed at `_bufl` `$4B2` — list 0 for FAT
sectors, list 1 for directory AND data sectors — filled by the boot at `0xFC4AFE` (`$8846` and
`$886E`). `0xFC5A98` is the whole of its policy: **MRU to the front, LRU at the tail**. A hit is
moved to the head after `Mediach` has been asked whether the medium is still the one those bytes
came off (0 = no, 1 = re-read the sector in place, 2 = `E_CHNG` and a longjmp); a miss takes an
EMPTY buffer if the scan passed one — the LAST such, because the scan's store is unconditional —
and otherwise the tail, flushes it if dirty, and fills it with one `Rwabs`. `$75B4` holds the last
BIOS disk result and `$87CC` the drive it came from; a non-zero result longjmps through the
process-termination record at `$7EF4`.

**The 8.3 NAME layer** touches no disk: `0xFC5D28` turns "name.ext" into the eleven padded FCB
bytes (`*` fills the rest of its field with `?`; a stem past eight is truncated and the remainder
thrown away up to the next `.`, `\` or NUL; a SPACE ends a field), `0xFC5C9A` compares one such
pattern with one directory entry (`?` matches anything except against a DELETED `$E5` entry, where
only an `$E5` pattern matches — which is how a free slot is found), and `0xFC50CA` is the
`and.w #$5f` fold, applied to both sides.

**FAT12 IS READ BIG-ENDIAN AND THEN SWAPPED.** `0xFC6038` seeks the FAT's pseudo-OFD to byte
`n + n/2`, reads two bytes, calls the byte-swapper at `0xFC4F10`, and then masks (`& $fff`) for an
even cluster or shifts (`>> 4`) for an odd one — which is how a 68000 reads a little-endian on-disk
FAT. `0xFC5F44` writes one back the same way round, and `0xFC60F2` is the chain walk with the
free-cluster search (a wrapping scan bounded by `m_numcl`) under it.

**THE PROCESS and its HANDLES** (`0xFC5216`, `0xFC52DE`, `0xFC56C6`, `0xFC7FD8..0xFC85D4`),
established by the recreate's GEMDOS process group (`recreate/src/gemdos/process.c`, `handles.c`,
`recreate/include/gemdos/process.h`).

**A HANDLE IS THREE DIFFERENT THINGS SPELT AS ONE SIGNED WORD**, and every routine in the group
branches on which: NEGATIVE is a character DEVICE (-1/-2/-3 = CON:/AUX:/PRN:, which is what a fresh
`p_uft` holds); 0..5 is a STANDARD handle, an index into the running process's own `p_uft` whose
byte is then one of the other two kinds; and 6 and up is a slot of the **HANDLE TABLE at `$8092`**,
75 records of ten bytes indexed from handle 6.

| handle-table field | what | evidence |
|---|---|---|
| `+0` | what the handle NAMES — the file system's own 64-byte OFD (above), or a NEGATIVE character device | `Fclose` `0xFC571C` and the dispatcher's resolution `0xFC995C` both branch on its SIGN |
| `+4` | the basepage that owns it, which is what makes it releasable by process | `Fdup` `0xFC526C` stores `p_run`; `0xFC80CE` hunts a dying process's |
| `+8` | a word REFERENCE COUNT | `Fforce` `0xFC538A` bumps it, `Fclose` `0xFC5730` drops it and zeroes the record at zero |

`Fdup` ($45) takes the first record nobody owns and copies `+0` but **not** the reference count — it
starts its own at one, so a program that `Fdup`s a file and closes both halves closes the file
twice. `Fforce` ($46) is four instructions over `0xFC52F8`, whose third argument is the basepage —
which is why `Pexec` can force a handle into the CHILD's table while `p_run` is still the parent's.

**The rest of the BASEPAGE this group established**, beside the `+$20`/`+$24`/`+$30`/`+$36` fields
the trap-entry wave found: `p_curdir` at **`+$40`, sixteen bytes**, one DIRECTORY NODE per drive
(`0xFC83DE`, `0xFC80EA`), and the COMMAND TAIL at **`+$80`, 128 bytes**, which `Pexec` also points
`p_dta` at (`0xFC83B2`). The trap entry's save slots hold more than D0: `Pexec` seeds `+$70` with
`p_bbase` and `+$74` with `p_dbase` (`0xFC85A4`/`0xFC85B2`), so a child starts with **A4 = BSS and
A5 = DATA** — the register contract every Atari `.PRG` of the period was linked against.

**`$8066` IS NOT "one flag byte per process slot"** — the earlier reading above is corrected here.
`0xFC51DE` bumps `$8066[node]` and `0xFC80EA` drops it, in both cases with `node` read out of a
basepage's `p_curdir`, so it is **one reference count per DIRECTORY NODE**, and `$7DEE` beside it is
the node table those counts are about. The dispatcher's arm at `0xFC952A` reads the same pair, and
what it is is now legible too: it fires when the longjmp comes back with **`E_CHNG` (-14)**, the
media-change error the buffer cache raises, and it invalidates every node on the changed drive.

**`Pterm` DOES NOT LONGJMP**, which is worth writing down because the record's name says it should.
`0xFC4F38` is a real `setjmp` and `0xFC4F54` a real `longjmp`, the dispatcher arms the record at
`$7EF4` and the FILE SYSTEM's critical-error abort is what jumps to it. `Pterm`'s own unwind is:
`Setexc($102, -1)` and a call through what came back, a Mega ST battery-clock re-read (`0xFC5092`,
the one piece of hardware GEMDOS itself touches), `p_run := p_parent`, the release at `0xFC8092`,
the exit code ZERO-extended into the parent's own `+$68` save slot, and `jsr $fc4fe8` — the trap
entry's epilogue, whose `rte` resumes whoever called the PARENT's GEMDOS call. `Ptermres` ($31) is
`Mshrink(p_run, keep)` and then the same walk with the descriptors handed back to the **record pool**
rather than to the free list, which is the whole of what "stay resident" means: the memory survives
with no owner and on no list.

**`Pexec`'s four modes are not a range** (`0xFC817E`): 0 LOAD AND GO, 3 LOAD, 4 JUST GO, 5 CREATE
BASEPAGE, with 1 and 2 a gap. It saves the dispatcher's termination record to `$7560` and arms one
of its own before any of them. The TPA is cut in TWO allocator calls — ask for the largest free
block, then ask for exactly that — and the environment is measured to its double NUL, rounded up to
a word, and copied into a block of its own. Two branches in it are DEAD CODE: the `mode == 4` half of
the owner choice at `0xFC8342` and the `cmpi.w #5` at `0xFC85C0`, both of them on paths only modes 0
and 4 reach.

### vdi + linea — `0xFC9F0C..0xFD2F21`

**Line-A** (`$28` := `0xFC9F0C`) reads the faulting `$aXXX` word, masks the low 12 bits,
bounds-checks against 15 and jumps through the 16-entry table at `0xFC9F4A`, advancing the
stacked PC past the word (`0xFC9F16`). `$a000` (`0xFC9F34`) returns the three values the ABI
promises: `a0` = the Line-A variable block at **`0x299A`** in RAM, `a1` = the three font
headers at `0xFC9F8A`, `a2` = the function table itself.

| opcode | routine | opcode | routine |
|---|---|---|---|
| `$a000` init | `0xFC9F34` | `$a008` TextBlt | `0xFCEE54` |
| `$a001` put pixel | `0xFCFACE` | `$a009` show mouse | `0xFCB120` |
| `$a002` get pixel | `0xFCFB16` | `$a00a` hide mouse | `0xFD0254` |
| `$a003` line | `0xFCA1EA` | `$a00b` transform mouse | `0xFD02CA` |
| `$a004` horizontal line | `0xFCA57E` | `$a00c` undraw sprite | `0xFD0184` |
| `$a005` filled rectangle | `0xFCFC56` | `$a00d` draw sprite | `0xFCFFB0` |
| `$a006` filled polygon | `0xFCA05E` | `$a00e` copy raster form | `0xFD0346` |
| `$a007` BitBlt | `0xFD05FC` | `$a00f` contour fill | `0xFD08F4` |

**The VDI** is entered from the GEM trap at `0xFC9F9E`. It copies the caller's five-array
parameter block (pointed at by `d1`) into the VDI's own RAM at **`0x299E`**, copies `ptsin`
to **`0x19DA`** (capped at 512 words, `0xFC9FD2`), calls the dispatcher `0xFCA9F6` and
returns the word at **`0x171E`**. The dispatcher finds the workstation by handle — the
device-block walk at `0xFCAA28` starting from `0x7F2E` and following `+0x40` — loads about
twenty attribute variables into the `0x26xx..0x2Axx` RAM block, then indexes the two opcode
tables. Opcodes **1** and **100** skip the workstation lookup (`0xFCAA18`), which is what
lets `v_opnwk`/`v_opnvwk` run before a handle exists.

Four opcodes are no-ops pointing at the bare `rts` at `0xFCA652`: 4 `v_updwk`, 10
`v_cellarray`, 27 `vq_cellarray` and the unused 34.

**The rasterizers can drive the blitter.** Six of them load a blitter register into `a5`
(`lea $00ff8a3c,a5` at `0xFCA20A`, `0xFCA5CA`, `0xFCEE6A`, `0xFCFCCC`, `0xFD0674`, and into
`a4` at `0xFCF9BE`), as do four sites in the VDI escape / raster helpers at `0xFC47BE`,
`0xFC4852`, `0xFC48B6`, `0xFC4936` — and XBIOS 64 `Blitmode` (`0xFC0EF6`) is implemented. So
TOS 1.02 is a blitter-aware ROM, and a recreate of these routines has two paths to reproduce,
not one. All ten sites address the chip through the **24-bit alias** `$00FF8Axx`, which is
why `RomLoader` creates that block ("Where the hardware really is").

Authorship is genuinely mixed (91 `link a6` for 199 functions): the rasterizers are asm
(`$a003` line, `$a007` BitBlt, `$a008` TextBlt — the 2,820-byte block at `0xFCEE66` that no
function body covers is inside TextBlt and holds its tables and the
`'Dave StaUgas loves Bea Hablig'` easter egg at `0xFCF716`), while the attribute and enquiry
opcodes are C.

### aes — `0xFD9ECA..0xFEE8FF` (shared with the desktop), table `0xFEF834`

Two `trap #2` handlers exist in sequence. Before the AES is up, `0xFC4EBC` (installed at
`0xFC4E72`) serves only the VDI: `d0 == 0x73` → `jsr 0xFC9F9E`, `d0 == -1` returns that
address in `d0`, anything else chains to the previous vector saved at `0x16D6`. Once the AES
initialises, `0xFE3EA6` (installed at `0xFE3C78`) takes `$88`: `d0 == 0xC8/0xC9` → the AES
entry `0xFE65AA`, `d0 == 0` → GEMDOS `Pterm(0)` (`0xFE3EC0`), anything else chains to
`0x8C2A`.

`0xFE65AA` marshals through `0xFE64E6` (copy the caller's `contrl`/`intin`/`addrin` arrays
into local frames, call, copy `intout`/`addrout` back) and the opcode switch is `0xFE5D9C`:
`sub #10 / cmp #115` at `0xFE64BA` bounds the opcode to **10..125**, then
`jmp *(0xFEF834 + 4*(op-10))`. 48 of the 116 entries are the unimplemented arm `0xFE64A6`,
and they are exactly the gaps in the published AES numbering. Two opcodes — 73 `graf_growbox`
(`0xFE6216`) and 108 `wind_calc` (`0xFE63AE`) — are arms *inside* the dispatcher's own body
rather than separate functions, which is why `names.txt` carries them as `cmt` lines.

AES init is at `0xFD9F2E`: it Malloc's the Line-F handler buffer, installs `$2c`, clears the
globals at `0x9C58` (`0xFD9F78`), parks pointers at `0x947A`/`0x947E`, and installs
`0xFE3F3E` into `0x8C32`. The AES's RAM is the `GEMBSS` block `0x8900..0xC9FF` that
`RomLoader` creates from the MUPB: the process/UDA area at `0x9C58` (`0xFD9FAA` adds `0x74A`
to it for the stack), the current-process pointer at `0xC794` (read at `0xFE3ED8` and
throughout), and `0x8C2A`/`0x8C32`/`0x8C36`/`0x8C3A` around the trap handler.

### desk — inside `0xFD9ECA..0xFEE8FF`; the boundary is NOT established

What is established: the desktop's **data** is the block
`0xFD83BF..0xFD9EC9` — the `'HDESKUSA.RSC'` name at `0xFD83BF`, the menu titles
(`' Desk '` `0xFD83FE`, `' File '` `0xFD8405`, `' View '` `0xFD840C`, `' Options '`
`0xFD8413`), every dialog and alert string through `0xFD92D3`, the `GEM, Graphics
Environment Manager` / `Copyright (c) 1986, 1987` / `Digital Research, Inc.` /
`Atari Corporation` info box at `0xFD8634..0xFD86C7`, the **default `DESKTOP.INF`** text
at `0xFD98CC..0xFD9AD8` (`#a`/`#b`/`#c`/`#d`/`#E`/`#W`/`#M`/`#T`/`#F`/`#G`/`#P` lines, which
is where the ROM's initial icon layout and `*.APP`/`*.PRG`/`*.TOS`/`*.TTP` associations come
from), and the FORMAT/DISKCOPY dialog at `0xFD9DEA..0xFD9EC9`. The code that reads
`"\DESKTOP.INF"` (`0xFEF348`) is at **`0xFDA444`**.

What is **not** established is where the desktop's code begins and the AES's ends. Three
signals were tried and all three failed to separate them, which is worth recording so nobody
repeats them: (a) pointers from the text into each resource block — there is exactly one in
the whole GEM text (`0xFEB3AA`), so the resources are reached through a base pointer, not by
address; (b) callers of the AES entry `0xFE65AA` — it has exactly one reference, the trap
handler at `0xFE3F00`, so the desktop does *not* call the AES through its public entry; (c)
a RAM-usage split per 4 KB — both halves touch the same `0x8900..0xC9FF` block. The likely
cut is a call-graph partition rooted at the desktop's `main`, which needs the naming loop,
not the bootstrap. Candidate marker for that work: the 45-entry switch table at `0xFEFB88`
whose targets `0xFE97AC..0xFEA832` have the shape of a menu-item handler set.

### data — extracted from the local ROM at build time

**The three system fonts.** `0xFC9F8A` holds the three header pointers Line-A `$a000` returns
in `a1`. Each is an 88-byte standard font header, and they chain contiguously:

| font | header | `off_table` | `dat_table` | form | span |
|---|---|---|---|---|---|
| `6x6 system font` | `0xFD39F6` | `0xFD3A50` | `0xFD3C52` | 192×6 | `0xFD39F6..0xFD40D1` |
| `8x8 system font` | `0xFD40D2` | `0xFD412C` | `0xFD432E` | 256×8 | `0xFD40D2..0xFD4B2D` |
| `8x16 system font` | `0xFD5B2E` | `0xFD412C` (shared) | `0xFD4B2E` | 256×16 | `0xFD4B2E..0xFD5B85` |

All three are `id=1`, `first_ade=0`, `last_ade=255`. Header fields read at `+0` id, `+2`
point size (8/9/10), `+4` 32-byte name, `+36/38` first/last ADE, `+40..48`
top/ascent/half/descent/bottom, `+50/52` max char and cell width, `+54/56` left/right offset,
`+58` thicken, `+60` underline size, `+62` lighten mask (`0x5555`), `+64` skew mask, `+66`
flags, `+68/72/76` hor/off/dat tables, `+80/82` form width and height, `+84` next font. The
8×16's `next_font` is `0` and the 8×8's is `0x000087D4` — a RAM address, i.e. the font ring
is re-linked at init. **The 8×16 font shares the 8×8's offset table**, which is the
verification that the two really are one 8-pixel-wide family.

**The keyboard scancode tables**: three 128-byte tables at **`0xFC2288`** (unshifted),
**`0xFC2308`** (shifted) and **`0xFC2388`** (CapsLock), ending at `0xFC2407`. `Bioskeys`
(`0xFC305A`) writes those three addresses into the `keytbl` struct at `$0E62`; `Keytbl`
(`0xFC302E`) replaces any of the three whose argument is non-negative and returns `$0E62`.
The tables are verifiable by eye: scancode `0x10` is `'q'`, and `0xFC2288+0x10 = 0xFC2298`
is the string `qwertyuiop[]` (`0xFC2318` `QWERTYUIOP{}`, `0xFC2398` `QWERTYUIOP[]`).

**The boot palette**: 16 words at `0xFC06A8`, copied to `$ffff8240` at `0xFC00C0`.

**The two embedded GEM resources** are described under `desk` above; the AES's own
(`'GEMUSA.RSC'` at `0xFD6F3E`) holds the file selector (`'ITEM SELECTOR'` `0xFD6630`) and the
AES alert strings (`0xFD698F..0xFD6F0C`). Their exact header offsets and object trees were
**not** parsed — the resources are pre-fixed-up in ROM and the `rsrc_gaddr` path that indexes
them was not read.

**Other data blocks no function body covers** (≥ 256 bytes): `0xFC0846` (the BIOS/XBIOS
tables), `0xFC2226`, `0xFC29FC`, `0xFC4308`, `0xFC47BE`, `0xFCA41A`, `0xFCEE66`, `0xFCFCD2`,
`0xFD0640` (holds `'JIM LOVES JENEANE'`), `0xFD1038`, `0xFD1A72`, `0xFD274E`, `0xFDEBF8`,
`0xFDEE0A`, `0xFE2066`, `0xFE27FC`, `0xFE5346`, `0xFE5C96`, `0xFE97D2`.

## RAM the components own

`RomLoader` creates four RAM blocks from the ROM's own numbers: `RAM_VEC` `0x0..0x3FF` (the
vector table), `SYSVAR` `0x400..0xFFF` (the system variables, **volatile** — see below),
`RAM` `0x1000..0x88FF` (up to `os_end`, OS header `+0x0c`) and `GEMBSS` `0x8900..0xC9FF` (the
MUPB's second longword). `SYSVAR` is volatile because an interrupt handler writes `_frclock`,
`_hz_200` and the three iorec records at `$C54`/`$C76`/`$D84` behind the code that polls them:
on a non-volatile block the decompiler folds the poll away, and `Vsync` `0xFC07D0` comes out
as `do { } while (true)` rather than as a loop on `_frclock`. Within them, what this bootstrap
established:

| range | owner | evidence |
|---|---|---|
| `$0..$3FF` | boot (vector table) | the installs tabulated under `boot` |
| `$380..$3CF` | the bombs handler | `0xFC0B5A` dumps `d0`–`a7` to `$384`, PC to `$3C4`, USP to `$3C8` |
| `$400..$5B3` | BIOS/boot (system variables) | the standard block; all 74 are labelled in `names.txt` |
| `$0E61..$0E6D` | BIOS keyboard | `pkbshift` (header `+0x24`), `keytbl` struct (`0xFC3052`) |
| `$0E8A..$0E91` | XBIOS sound and printer state | `Dosound` reads/writes `$0E8A`/`$0E8E` (`0xFC3074`); `Setprt` uses `$0E90` (`0xFC3088`) |
| `$16CE`, `$16D2`, `$16D6` | GEMDOS/GEM entry glue | supervisor stack (`0xFC4FB8`), saved `trap #2` vector (`0xFC4E68`) |
| `$171E`, `$19DA`, `$299A`, `$299E`, `$26xx..$2Axx` | VDI + Line-A | `0xFC9FF4`, `0xFC9FAA`, `0xFC9F34`, `0xFC9FA4`, `0xFCAA40`+ |
| `$2994` | console/cursor state shared by BIOS and VDI escape | `0xFC427A`, `0xFC4698` |
| `$7F2E` | VDI workstation list head | `0xFCAA28` |
| `$7E9C`, `$8380`, `$87CC`, `$87CE` | GEMDOS | OS header `+0x20`/`+0x28`, `0xFC9534`, `0xFC952A` |
| `$8900..$C9FF` | GEM (AES + desktop) | the MUPB; `0x9C58` `0xFD9F78`, `0xC794` `0xFE3ED8` |

The **exact** extent of each component's BSS was not established — nothing in the ROM
declares it, and deriving it needs the post-boot RAM snapshot the recreate harness is going
to capture anyway.

## Known gaps in this bootstrap

* **73 functions fail to decompile** ("Low-level Error: Cannot properly adjust input
  varnodes"), among them `Fread` `0xFC5E6A`, `Fwrite` `0xFC5EEA`, `Pexec` `0xFC817A`,
  `Mshrink` `0xFC895A`, `Setexc` `0xFC0A72`, `Flopfmt` `0xFC1916`, `Mfpint` `0xFC2658`,
  `Initmous` `0xFC2F28`. The list is regenerable with
  `grep -B2 'decompile failed' decomp.c`. They are *listed and disassembled*, only not
  decompiled. The common shape is the Alcyon argument-passing idiom — the caller writes the
  first argument into the already-allocated slot at `(sp)` (`0xFC5E72`
  `move.w 8(a6),(sp)`) instead of pushing it — which defeats Ghidra's stack analysis. No
  workaround was tried; the disassembly is the fallback for all 73 (the eight named above are
  examples, not the list).
* **A Line-F call decompiles as nothing at all.** The callee's return value in `d0` and its
  register clobbers are invisible, so any expression reading `d0` after a site is wrong, not
  merely missing. Every site carries a pre-comment saying so. This is the same trade
  `LineAResolve` makes for Line-A (`docs/ghidra-pipeline.md`).
* **Line-F words a branch jumps to directly are not resolved** — only fall-through sites are.
  `LineFResolve` counts them at the end of each run (`unresolved Line-F words reached by a
  branch/call, NOT handled: 32`) and lists the first 32; the other symptom is the
  `WARN … Unable to resolve constructor` lines in the bootstrap log.
* **`LineFResolve` prints a "could not re-body" warning for ~300 functions.** They are
  functions that end at a Line-F *return* word, where the next address is the next function's
  entry; the body is already correct and the warning is noise, but it is loud noise.
* **Two seeds never become functions** — `0xFE6216` (AES 73 `graf_growbox`) and `0xFE63AE`
  (AES 108 `wind_calc`) are arms inside `aes_dispatch`'s body, and `ApplyNames` cannot create a
  function inside an existing one. `names.txt` carries them as `cmt` lines for that reason, so
  the name map itself applies cleanly; `gen_seeds.py` still emits them and they are the whole of
  the difference between its 903 lines and the 901 functions they create.
* **The aes/desk code boundary**, the resource object trees, and the per-component BSS
  extents are open, as described above.
