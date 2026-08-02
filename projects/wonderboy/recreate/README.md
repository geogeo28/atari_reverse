# Wonder Boy in Monsterland — differential reconstruction

Readable C for *Wonder Boy in Monsterland* (Atari ST, Activision 1989), each function to be
**proven byte-for-byte equivalent to the original 68000 code**. This is the *recreate* track:
faithfulness beats correctness every time, so original bugs are reproduced rather than fixed.

The machinery is shared — [`tools/recreate_kit`](../../../tools/recreate_kit/README.md) loads the
`.PRG` into a flat image, runs the original under a Musashi 68000 oracle and this project's
compiled C on the same image, and diffs the result. Everything game-specific lives here. For *why*
the method is differential rather than byte-matching, read the worked reference project,
[`projects/buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md).

**Nothing is reconstructed yet.** What exists is the binding plus a foundation battery that runs the
original code under the oracle and pins how the program starts. Progress, the kit change this
project required, and the three blockers between here and a first reconstructed function:
[`STATUS.md`](STATUS.md).

```
project.toml               binds this directory to the kit (paths, load base, image size, two waivers)
Makefile                   three lines: KIT + GAME + include $(KIT)/kit.mk
include/wonderboy.h        how SWB.PRG becomes a running image, as constants — the canonical copy
src/                       the reconstruction's cores, one file per subsystem. EMPTY: there are none
                           yet. The candidate .so still builds and links, out of the kit's own
                           src/*.c alone (the Dosound ledger and the refused-os_*-call tally that
                           every candidate must export)
test/harness.py            the kit-binding shim
test/layout.py             include/wonderboy.h's constants, scraped from that header (one source of truth)
test/test_layout.py        that scraper's own cases — it refuses a duplicate or an octal-ambiguous #define
test/test_bootstrap.py     the foundation battery: the loader, the self-relocation, the trap inventory
test/test_poked_input_guard.py  the kit waiver this project is the only user of, and its three guards
```

## Running

```bash
make venv      # once: .venv + pytest/pytest-xdist (see requirements.txt)
make test      # build the candidate + the shared oracle, run the suite across cores
make oracle    # rebuild only the shared Musashi oracle
make clean     # this project's build/ only — the oracle is shared, see the kit README
```

`make venv` is `python -m venv .venv` plus `pip install -r requirements.txt` (`kit.mk`), the same
two lines BuggyBoy and Joust use — run it with the `atari_reverse` conda Python. The `.venv` already
in this directory was instead made the way Joust's was,
`python -m venv --system-site-packages .venv`, which borrows pytest and pytest-xdist from that conda
environment rather than installing its own copies. Either form works; `requirements.txt` is the
canonical list of what has to be reachable.

## The binary, and the one thing that makes it unusual

`../bin/disk1/AUTO/SWB.PRG` is the ORIGINAL, uncracked release, extracted from the Pasti `.stx`
images with `tools/stx_extract.py`. 136,979 bytes: text `0x214d8`, no data, no bss, entropy 4.96
(plain code+data, not packed). `bin/` is gitignored — no game data is committed.

**The program is not position-independent.** 136 KiB of text carries **three** relocation entries,
and the body addresses itself with absolute long operands (`jsr $e032.l`, …) that nothing fixes up.
The entry point is a trampoline into a relocator at the very end of the text:

```
+0x00000  3000                 move.w  d0,d0
+0x00002  4ef9 000213e0        jmp     $213e0.l           <- RELOCATED
...
+0x213e0  2f3c 000214d8        move.l  #$214d8,-(a7)      <- RELOCATED
+0x213e6  3f3c 0020            move.w  #$20,-(a7)
+0x213ea  4e41                 trap    #1                 ; GEMDOS Super(end of program)
+0x213ec  46fc 2700            move.w  #$2700,sr
+0x213f0  43f9 00000400        lea     $400.l,a1          ; NOT relocated — an absolute address
+0x213f6  41f9 00000008        lea     $8.l,a0            <- RELOCATED
+0x213fc  203c 000084f6        move.l  #$84f6,d0          ; 0x84f6 longwords = 0x213d8 bytes
+0x21402  22d8 5380 66fa       move.l (a0)+,(a1)+ ; subq.l #1,d0 ; bne
+0x2140a  4ef9 00000400        jmp     $400.l
```

So the program **copies itself to the fixed absolute address `0x400` and runs there**. The only
address space in which a reconstruction can be verified is that runtime one.

### Why `load_base = 0x3f8`, and not the workspace default

`0x3f8 + 8 == 0x400`. At that base the loaded image **is** the runtime image: the relocator's source
and destination coincide, its copy is an identity copy, and the game's own absolute operands address
the loaded image directly with no staging step. It is also the base `../names.txt` is written at —
the kit reads that file for its diff labels and its exclude-band vetting, so a base that disagreed
with it would mislabel every future report — and the base at which Ghidra recovers 186+ functions
rather than 57. Every line of the listing above is verified: the relocator is run under the oracle
in `test_the_relocator_copies_the_body_to_its_runtime_base`, with the destination compared against
the file's own bytes (no relocation fixup lands inside the copied body, so the runtime bytes ARE the
raw file bytes).

Two consequences worth knowing before touching anything:

* **`../run.sh` passes `0x3f8`**, so re-bootstrapping Ghidra lands in the same address space as
  `../names.txt` and this directory. It still re-imports and wipes the DB — iterate with
  `../reapply.sh`.
* **`0x3f8` is below the kit's `load_base >= 0x620` floor**, which is why the kit gained a second
  waiver (`tos_poked_input_unused`) and two guards that enforce its claim per poke and per run.
  [`STATUS.md`](STATUS.md) describes them and `test/test_poked_input_guard.py` pins them.

## One trap in the whole image

The game issues **exactly one** TOS call — the GEMDOS `Super` above — and drives the hardware
directly for everything else, including the floppy: it loads `OVALAY*.RAD` / `TILEDATA.RAD` /
`SPRITES.CRU` / `DATADISK.RAD` by name (the strings are at file offset `0x21226`) with no GEMDOS
file call anywhere. Established by an exhaustive byte scan of all sixteen `trap #N` encodings at
every even offset: five exist, four of them inside the game's ASCII message tables
("MYCO**NI**D MASTER!", "RED K**NI**GHT!", "GIANT CO**NG**!"). The five are pinned by offset *and*
classified by a printable-run rule, so neither the list nor the rule stands alone.

That single fact carries both of `project.toml`'s waivers — a `Malloc` and a poked-input read alike
need a trap, and there is only this one, and it is a `Super`. It also means the kit's trap model
**refuses** this game's `Super`, whose argument is the program's own end address rather than `0`,
`1` or the model's cookie (`TRAP_MODEL.md`, Phase 2). That costs nothing today, because the oracle
already runs in supervisor mode and a run can simply enter one instruction later at
`WB_RELOCATOR_COPY_OFF`; it is pinned as a case so a change to the model shows up as a failing test
rather than as a silently different run.

Direct hardware access is also where the harder wall is. The kit rejects any direct PSG *read*
outright, which is what an ST floppy drive-select does — the wall that put Joust's raw-floppy
routine off its list. How much of this game sits behind it has not been measured.
