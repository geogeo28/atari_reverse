# Bubble Ghost — the protection wrapper on GHOST.PRG, and GHOST.LOA

*ERE Informatique, 1987. All addresses in this file are **image offsets** (file offset minus the
28-byte GEMDOS header) unless a "Ghidra" address is given, in which case add the `0x10000` load
base the project uses.*

## The seven files on the disk

| file | size | what it is |
|---|---:|---|
| `GHOST.PRG` | 61,032 | the game, wrapped in a disk-protection **encrypter** (this document) |
| `GHOST.LOA` | 2,703 | a standalone **digitised-sample player**, loaded as data and `jsr`ed |
| `GHOST.VOI` | 30,100 | the sample `GHOST.LOA` plays (`0x7594` bytes, the length in its header) |
| `GHOST.DAT` | 184,352 | six 320×192 low-res pictures (`6 × 0x7800`) + a 32-byte palette |
| `GHOST.PRE` | 30,752 | one 320×192 picture (`0x7800`) + a 32-byte palette — the presentation screen |
| `GHOST.DEM` | 6,000 | the recorded attract-mode demo (`0x1770` bytes) |
| `DESKTOP.INF` | — | French desktop settings; **no autostart line, and there is no AUTO folder** |

`GHOST.SCR` is *not* on the disk: the game creates it on drive A: the first time it saves the
hall of fame.

## Verdict, in one line

`GHOST.PRG` is **not crunched** — it is the same size as the program inside it. It is
**encrypted with a stream cipher whose 16-bit key is a CRC of the copy-protection track**, so the
check cannot be patched out: get the disk data wrong and you get rubbish, not a failed branch.

`tools/depack_bubbleghost.py` decrypts it statically, and
`projects/bubbleghost/tools/boot_ghost.py` proves the result byte-for-byte against a real run
(see "Verification" at the end).

---

## The entry stub

The shipped header says `text=0xe8ca data=0x57a bss=0x63ca sym=0`, **one** relocation entry, text
entropy **7.68** — the "likely packed" flag. The entry is five words:

```
000000: 206f 0004      movea.l 4(sp),a0        ; the basepage
000004: 6002           bra.s   $8              ; steps over two dead bytes
000008: 2068 0018      movea.l 24(a0),a0       ; a0 = p_bbase
00000c: 4ee8 fdb6      jmp     -$24a(a0)       ; -> image 0xebfa, in the DATA segment
```

`p_bbase` is `text+data`, so the wrapper's entry is at `0xee44 - 0x24a = 0xebfa`. Everything from
image `0x14` to `0xebca` is ciphertext; `0xebcc`–`0xee44` is the wrapper, of which only
`0xebcc`–`0xec1e` and `0xee2a`–`0xee44` are plaintext in the file.

The single relocation entry (image offset `0x10`) is inert — it lands inside the 20 bytes the
wrapper overwrites before they are ever executed. Its only job is to make the file look like an
ordinary relocatable `.PRG`.

---

## Layer 1 — the wrapper decrypts its own second half

```
00ebfa: 204f           movea.l sp,a0
00ebfc: 48e7 ff7e      movem.l d0-d7/a1-a6,-(sp)
00ec00: 2c48           movea.l a0,a6            ; a6 = the entry sp
00ec02: 61e8           bsr.s   $ebec            ; Super(0); d0 = the old SSP
00ec04: 40c6           move.w  sr,d6            ; SR here is $2300 (supervisor, IPL 3)
00ec06: 2e00           move.l  d0,d7
00ec08: 007c 0700      ori.w   #$700,sr
00ec0c: 43fa ffbe      lea     $ebcc(pc),a1     ; the key table
00ec10: 45fa 000c      lea     $ec1e(pc),a2     ; the first word to decrypt
00ec14: 323c 0105      move.w  #$105,d1         ; 262 words
00ec18: 3019           move.w  (a1)+,d0
00ec1a: b15a           eor.w   d0,(a2)+
00ec1c: 51c9 020e      dbf     d1,$ee2c         ; <-- see below
```

**The trap is the 68000's prefetch queue.** `a2` starts on the `dbf`'s *own* displacement word, so
the first `eor` rewrites it: `0x020e ^ 0xfdf4 = 0xfffa`, i.e. "branch back to `$ec18`". But the
68000 fetched that displacement before the `eor` stored it, so **pass one branches to the stale
target `$ee2c`** — plaintext code at the very end of the data segment:

```
00ee2c: 7410           moveq   #$10,d2
00ee2e: 5542           subq.w  #2,d2
00ee30: 4659           not.w   (a1)+            ; 15 words: the key table minus its first
00ee32: 51ca fffc      dbf     d2,$ee30
00ee36: 43fa fd94      lea     $ebcc(pc),a1     ; reset the key pointer...
00ee3a: 32bc 0000      move.w  #0,(a1)          ; ...and zero its first word
00ee3e: 6000 fdd8      bra.w   $ec18            ; re-enter the loop, a2 already advanced
```

So the real keystream is `[0, ~w1, ~w2, … ~w15, <the plaintext at 0xebec onward>, …]` and the
loop runs its remaining 261 iterations over `0xec20`–`0xee2a`. A model that ignores the prefetch
decrypts the whole run against the wrong keystream and produces garbage — this cost the first
attempt at a static decrypt.

The ones-complement also turns the key table into the wrapper's own data:

```
0xebcc  0000 00f7   -> buffer offset 0,      sector 247
0xebd0  0400 00f5   -> buffer offset 0x400,  sector 245
0xebd4  0600 00f6   -> buffer offset 0x600,  sector 246
0xebd8  4ef9 0000 0036   \
0xebde  4ef9 0000 52fa    |  the 20 bytes of the program's own jump table that
0xebe4  4ef9 0000 5136    |  the five-word entry stub displaced
0xebea  4ef9             /
0xebec  7000 2f00 3f3c 0020 4e41 5c8f 4e75   ; Super(d0) helper
```

## Layer 2 — the copy-protection check

Unpacked, `0xec20` onward reads (Ghidra-address-free, image offsets):

1. `movea.l 4(a6),a6` → the basepage; `movea.l 24(a6),a5` → `p_bbase`, used as a scratch buffer.
2. `suba.l a0,a0` then `move.w #$0f13,$24` / `move.w #$6f73,$26`. **The 68000 TRACE vector is the
   wrapper's key storage** — which doubles as an anti-debugger: single-stepping needs `$24`, and
   overwriting it destroys the key. (The value is also a plausible-looking odd address, so a
   trace exception on a debugged run dies with an address error.)
3. `Super(d7)` back to user mode.
4. Fill `a5+0x1fc … a5+0x21f` with nine `'HLS '` longwords — a sentinel that proves the floppy
   read really wrote there.
5. `Floprd(a5, 0, dev=d4, sect=1, track=79, side=0, count=9)` through this wrapper:

   ```
   00ecd6: 704f           moveq #$4f,d0     ; TRACK 79
   00ecd8: 7200           moveq #0,d1       ; side 0
   00ecda: 3f03 3f01 3f00 3f02 3f04         ; count, side, track, sector, device
   00ece4: 42a7 2f08 3f3c 0008 4e4e         ; filler, buffer, XBIOS Floprd
   ```

   `d4` is both the drive number and the retry counter: A: first, then B:, then give up.
6. Scan the 9 sectors for the word `$a1a1` followed by a byte `$fe` or `$fb` — those are **MFM
   address marks** (`A1 A1 A1 FE` = ID field, `FB` = data field), so the sector data on track 79
   is a dump of raw track bytes, not ordinary file data. Also require that the `'HLS '` sentinels
   were overwritten.
7. Read three more single sectors from the same track: **sector 247 → `a5+0`, 245 → `a5+0x400`,
   246 → `a5+0x600`** (the coordinates from the ones-complemented key table). Each read must
   return either 0 **or exactly `-4` (CRC error)** — anything else, notably the `-8`
   "sector not found" a normally formatted disk gives, fails. That is the whole trick: those
   sector IDs must *exist* on the track, and their data is allowed to be unreadable (fuzzy bits +
   bad CRC), which is precisely what an ordinary copier cannot reproduce.
8. Copy 512 bytes from `a5+0x1000` down to `a5+0x200`, so the CRC input is
   `[247][sector 9][245][246]`.
9. **CRC #1** over 842 words from `a5` (1,684 bytes): a plain MSB-first LFSR, seeded from `$24`
   and using the word at `$26` as the polynomial. The result is stored back into `$26`.
10. **CRC #2** over 316 words from `0xebcc` (632 bytes = the whole wrapper through the end of the
    image), with CRC #1 as the polynomial. So the key depends on the disk **and** on the
    wrapper's own bytes: patch one instruction in the loader and the game decrypts to noise.

    The result is `d3` = **`0x586b`**.

On any failure the code jumps to `0xee18`, wipes `0x96` longwords of itself and calls `Pterm0`.

## Layer 3 — the stream cipher over the program

```
00ed6e: 41fa fe68      lea     $ebd8(pc),a0
00ed72: 226e 0008      movea.l 8(a6),a1         ; a1 = p_tbase
00ed76: 7209           moveq   #9,d1
00ed78: 32d8           move.w  (a0)+,(a1)+      ; restore the displaced 20-byte jump table
00ed7a: 51c9 fffc      dbf     d1,$ed78
00ed7e: 243c 0000 75dc move.l  #$75dc,d2        ; 30172 words
00ed88: 023c 0000      andi.b  #0,ccr           ; X := 0
00ed8c: 600c           bra.s   $ed9a
00ed8e: 3019           move.w  (a1)+,d0         ; d0 = the PRECEDING plaintext word
00ed90: 40c1           move.w  sr,d1            ; ...and the flags that load just set
00ed92: b340           eor.w   d1,d0
00ed94: b740           eor.w   d3,d0
00ed96: b151           eor.w   d0,(a1)          ; decrypt the next word
00ed98: e253           roxr.w  #1,d3            ; rotate the key through X
00ed9a: 51ca fff2      dbf     d2,$ed8e
```

i.e. `plain[i+1] = cipher[i+1] ^ plain[i] ^ SR ^ k[i]`, `k` rotated right through X each word,
starting at image `0x14` and running to `0xebcc` (`0x14 + 2·0x75dc`). `SR` is `0x2300 | X<<4 |
N<<3 | Z<<2`, with N and Z left by the `move.w (a1)+,d0` — **the CPU's own condition codes are
part of the keystream**, which is why the decrypter has to model them. The IPL is 3, not the 7
set at `0xec08`, because `move.w d6,sr` at `0xec20` put the entry SR back first.

`0x586b` is the only one of the 65,536 possible keys that yields a valid image; the depacker
carries it as a constant and re-validates the result rather than re-deriving it (deriving it
needs the floppy).

## Layer 3b — the basepage patch and the buried relocation table

```
00eda8: 2a3c 0000 0286  move.l #$286,d5
00edae: 9bae 0014       sub.l  d5,20(a6)      ; p_dlen  0x57a -> 0x2f4
00edb2: 9bae 0018       sub.l  d5,24(a6)      ; p_bbase -> image 0xebbe
00edb6: 203c 0000 6650  move.l #$6650,d0
00edbc: 2d40 001c       move.l d0,28(a6)      ; p_blen  0x63ca -> 0x6650
00edc0: …               the ordinary DRI relocation loop, reading its stream from p_bbase
```

The original linker's relocation table was moved to sit right after the real data, and the
wrapper was laid down on top of everything after it. `p_bbase - 0x286` points back at it. It is
only 13 bytes: nine fixups, six bytes apart — the nine `jmp $xxxx.l` operands of the jump table
at TEXT+0. **The rest of the program is position-independent** (PC-relative code, `a4`-relative
data), which is why an unpacked Bubble Ghost has just nine relocations.

Finally the wrapper copies its exit sequence onto the stack, zeroes the BSS and `jmp (a0)` with
`a0 = p_tbase`.

## The rebuilt executable

`tools/depack_bubbleghost.py` reassembles all of the above into an ordinary `.PRG`:

```
$ python3 tools/depack_bubbleghost.py projects/bubbleghost/bin/GHOST.PRG \
      -o projects/bubbleghost/bin/GHOST_PLAIN.PRG
  61032 packed -> 60391 bytes  |  first 16: 601a0000e8ca000002f4000066500000
```

| | packed | plain |
|---|---:|---:|
| text | `0xe8ca` | `0xe8ca` (of which `0x14`–`0x71d2` is code and `0x71d2`–`0xe8ca` is graphics data) |
| data | `0x57a` | `0x2f4` |
| bss | `0x63ca` | `0x6650` |
| relocations | 1 | 9 |
| text entropy | 7.68 | 5.36 |

Load base for the project is the workspace default `0x10000`; under Hatari (TOS 1.04, 1 MB, run
from a GEMDOS drive) the real base was `$12596`.

---

## GHOST.LOA — the digitised-voice player

A separate, **`ABSFLAG`-set** (no relocation table) `.PRG` that the game reads whole into a
buffer and calls. It is not part of the protection at all; `tools/prg_dis.py` used to crash on it
because the file ends one byte into where a relocation table would start (now reported instead).

Header parameters, at text offset 2, ahead of a `bra.s` that steps over them:

```
0002: 0003 8ad4    sample address   <- the game overwrites this with its malloc'd VOI buffer
0006: 0000 7594    sample length    = 30100 = the size of GHOST.VOI
000a: 0000 0003    rate index       (0..7, into the Timer A table at text 0xa62)
```

The player: `Super(0)`, save MFP `IERA/IERB/IMRA/IMRB/VR/TACR/TADR`, install its own **Timer A**
handler at `$134`, program TACR/TADR from the rate table, unmask Timer A only, silence the PSG,
then spin until the sample ends. The per-sample ISR at text `0xa4` reads `(a6)+`, stops when it
passes the end, and otherwise `jmp (a5)` to one of two output routines:

* `0xc2` — **PSG volume playback**: `sample + 0x80`, `<<3`, index an 8-byte-per-entry table at
  `0x262` and `movep` register/value pairs at `$ffff8800`. (The entries hold three pairs —
  registers 8, 9 and 10 — but the second `movep` re-reads displacement 0, so only the first pair
  is emitted twice and channel C's value is never written. Recorded as observed; it looks like an
  original bug, and nothing in the game depends on it being right.)
* `0xde` — **cartridge-port DAC**: `move.b (0,a4,d7.w*2)` with `a4 = $fa0000`, the classic ST
  Replay-style digitiser where the address lines *are* the DAC. Selected by the alternative
  setup at `0x248`; the game only ever uses the PSG path.

The game side (`FUN_00013c6c` / `FUN_00013cea`, Ghidra `0x13c6c` / `0x13cea`) reads `GHOST.LOA`
into `a4-6010`, `malloc`s `0x7594` for `GHOST.VOI`, pokes that pointer into the LOA image at
`+0x1e` (28-byte header + text offset 2 = the sample-address field) and `jsr`s `a4-5982`
(= buffer + 28 = the LOA's text). It runs once, over the presentation screen, and the voice
buffer is freed right afterwards.

---

## Verification

`projects/bubbleghost/tools/boot_ghost.py` boots the Pasti dump in Hatari headless (`--disk-a
gw/dumps/bubble_ghost/bubble_ghost.stx`, TOS 1.04, 1 MB, RGB low res) with `GHOST.PRG` auto-run
from a GEMDOS drive C:. That is legitimate because the protection addresses drive A: **by device
number**, so the STX with its fuzzy bits stays in A: regardless of where the program came from.

```
$ python3 projects/bubbleghost/tools/boot_ghost.py
decrypted TEXT at $12596 7.8s after power-on; capture .../out/boot_title.png (2 distinct colours); hatari exit status 0
PROTECTION PASSED: the whole TEXT of GHOST_PLAIN.PRG is in the machine's RAM
```

**The protection passes under Hatari from this STX** — the emulator honours the track-79 sectors,
so the recreate can be verified on the emulator later without cracking anything. The gate is not
the picture: it is that the WHOLE TEXT produced *statically* by `depack_bubbleghost.py` (every
byte except the nine relocated longwords) was found verbatim in the emulated machine's RAM, which
pins the static decrypter against the real CPU as well — and the verdict also requires a clean
Hatari log, exit status 0 and a capture that is not blank.
