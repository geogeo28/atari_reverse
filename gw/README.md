# Atari ST floppy backup (Greaseweazle)

Backs up Atari ST floppies to preservation-grade images using a Greaseweazle V4.1
and the HxC command-line converter.

## Pipeline

The disk is spun **once**. Everything else is derived offline from that read, so a
fragile disk is never re-read just to produce another file format.

```
floppy ──gw read --raw──> .scp  (flux gold master, keep forever)
                           ├──hxcfe + track-image injection──> .stx  (Pasti; bootable 0x61, for Hatari)
                           └──gw convert──> .st  (plain sector image, unprotected disks only)
```

- **`.scp`** — raw flux, every revolution as the drive saw it. This is the *only*
  lossless record: weak bits, non-standard track lengths and protection all survive
  here. Keep it forever, even after converting to STX — an STX is an interpretation
  of the flux, and a better decoder next year can revisit the SCP but cannot
  un-bake an STX.
- **`.stx`** — Pasti image. What Hatari wants for a copy-protected game.
- **`.st`** — plain sector dump. Only meaningful when the disk verifies 100%.
  Protected disks are *expected* to fail this decode; that is not an error.

`--raw` is essential: without it `gw read` writes *decoded* sectors into the SCP,
which silently discards the protection you are trying to preserve.

## Tools

| Tool | Path |
| --- | --- |
| Greaseweazle host tool 1.23 | `/Users/geogeo/miniconda3/envs/atari_reverse/bin/gw` |
| hxcfe 2.16.13.1 | `/Users/geogeo/opt/hxcfe_cmdline/App/hxcfe` (needs `DYLD_LIBRARY_PATH=/Users/geogeo/opt/hxcfe_cmdline/Frameworks`) |

Device: Greaseweazle V4.1, firmware 1.6. The serial port is auto-detected; override
with `--device` if you have more than one plugged in.

Output lands in `dumps/<disk-name>/` (`.scp`, `.stx`, `.st`, `read.log`).

## Usage

```bash
./backup_disk.sh --preflight              # check tools + device, no drive access

./backup_disk.sh dungeon-master           # normal 720K disk
./backup_disk.sh xenon2 --protected       # protected: flux + STX only, no .st
./backup_disk.sh oldsave --rescue         # damaged disk: more revs + retries

./backup_disk.sh singlesided --format atarist.360
./backup_disk.sh partial --tracks 'c=0-79:h=0-1'
```

An existing dump directory is never overwritten without `--force`; `--force` clears
the previous run's `.scp`/`.stx`/`.st` first, so a stale file is never mistaken for
a fresh one.

`--convert-only <file.scp>` re-runs just the SCP → STX step on an existing dump.
This is also the recovery path for an interrupted read: a Ctrl-C'd `gw read` leaves
a partial SCP on disk, and whatever tracks it captured can still be converted.

With `--tracks`, a "100%" verification only covers the tracks you actually read —
it says nothing about the rest of the disk.

Formats (`gw` diskdefs): `atarist.360` `atarist.400` `atarist.440` `atarist.720`
`atarist.800` `atarist.880`. Default is `atarist.720`.

## Repairing a bad read

"Repair" means **aggressive re-reading**, not editing the image:

- Run `--rescue` (8 revolutions, `--retries 8`, `--seek-retries 3`). Seek retries
  re-home the head to track 0 and step back, which often recovers a marginal track.
- **Run it more than once.** Marginal flux transitions are probabilistic; a second
  or third pass frequently picks up sectors the first missed.
- **Clean the drive heads** (isopropyl on a lint-free swab) and try a different
  drive — head alignment varies between drives, and a disk written on a misaligned
  drive may only read back on a similar one.
- Check `read.log`: tracks are drawn as a map where `.` is a good sector and `X` a
  missing one, ending with `Found N sectors of M`. That map only exists for reads
  that decode a format — a `--protected` run has no map, because nothing is decoded.

Retries only work when a format is given, because `gw` decides a track needs
re-reading by decoding it and finding sectors missing. With `--protected` there is
no decode and therefore no retry loop — for protected disks the lever is more
revolutions, not more retries. Conversely, on a non-protected read each retry pass
is *appended* to the raw stream, so retries make the SCP gold master richer.

## Mounting a dump / file-level access

A `.st` is a raw FAT12 volume, so its files are reachable directly (both routes
verified with a write/read round-trip):

```bash
# mtools (brew install mtools) — no mounting, most tolerant of Atari boot sectors
mdir  -i disk.st ::               # list files
mcopy -i disk.st ::GAME.PRG .     # extract
mcopy -i disk.st file.txt ::      # insert

# native Finder mount — the imagekey tells hdiutil it is a raw image
hdiutil attach -readonly -imagekey diskimage-class=CRawDiskImage disk.st
```

If macOS refuses a TOS-formatted boot sector, mtools still works — prefix with
`MTOOLS_SKIP_CHECK=1` if it complains too.

A `.stx` is a flux-level container, not a filesystem — nothing mounts it directly.
Convert it down first, then mount the result:

```bash
DYLD_LIBRARY_PATH=~/opt/hxcfe_cmdline/Frameworks \
  ~/opt/hxcfe_cmdline/App/hxcfe -finput:game.stx -conv:ATARIST_ST -foutput:game.st
```

The filesystem decodes fine; the protection tracks do not survive. Extracting files
from a protected disk this way works — *running* the game still means giving Hatari
the STX itself.

## Finder Quick Actions

Two right-click actions, so a dump in `dumps/` can be opened or booted without a
terminal:

```bash
./install_quick_actions.sh              # install / refresh both
./install_quick_actions.sh --uninstall  # remove both
```

| Quick Action | Accepts | Does |
| --- | --- | --- |
| **Mount Atari ST Disk** | `.st` (one or many) | `hdiutil attach` each image, then open the volume in Finder |
| **Run in Hatari** | one `.st`, `.stx`, `.msa` or `.dim` | boot it in Hatari as drive A: and detach |

The installer writes two `.workflow` bundles into `~/Library/Services/`, then runs
`/System/Library/CoreServices/pbs -update` — without that refresh the menu items only
appear after the next login. Re-running the installer overwrites cleanly.

The bundles are deliberately stupid. Each one is a single Automator "Run Shell Script"
action containing one line, `exec <repo>/gw/qa_<action>.sh "$@"`, so all the real logic
lives in `qa_mount_st.sh` and `qa_run_hatari.sh` — versioned here, runnable from a shell,
and editable without regenerating a bundle:

```bash
./qa_mount_st.sh dumps/dungeon-master/dungeon-master.st
./qa_run_hatari.sh dumps/xenon2/xenon2.stx
```

Because the bundle path is baked in at install time, moving or renaming this repository
breaks both actions — re-run the installer afterwards.

**Mounting is read-only**, because right-click mounting is for looking, and a read-write
mount is not passive: one mount/unmount cycle of the test image let macOS write `.fseventsd`
into it, changing its SHA-1 and consuming 4 KB of its free space. Nothing irreplaceable is
lost when that happens — the `.scp` is the gold master — but an image that silently differs
from the one you dumped is a bad default in a preservation toolkit. To write to a disk, do
it deliberately: use the `mtools` commands above, or remove `-readonly` from the
`hdiutil attach` line in `qa_mount_st.sh`.

Eject when you are done, the same as any disk — drag the volume to the Trash, hit eject in
the Finder sidebar, or `hdiutil detach /Volumes/<name>`.

A selection can hold several images; each is mounted independently, and one that fails does
not stop the others — the notification reports how many of them mounted and the log names
each one that did not.

`.stx` is a flux container with no filesystem, so only Hatari accepts it; the mount action
rejects it with an explanation rather than a silent no-op. Hatari reads `.st`, `.msa`,
`.stx` and `.dim` directly, which is why it takes the wider set.

**Background — a *raw* hxcfe STX may not boot a copy-protected game.** hxcfe on its own writes
sector-only STX track records (track flags `0x01`), never the full track image (`0x61`) a
real Pasti dump carries. A protection that issues raw FDC READ TRACK commands gets a
synthesized standard track instead of its signature track and fails. Proven on Wonder Boy
disk 1: Hatari logs `fdc stx : no track image for read track ... building a standard track`
(then `too many data sector=10` — the 12-sector protection track does not even fit the
synthesized one) and the Copylock loader retries forever on a black screen. The `.scp` gold
master holds everything — the loss is purely in the conversion. **`backup_disk.sh` now closes
this automatically:** its STX step is `convert_scp_to_bootable_stx` (hxcfe + track-image
injection, below), so a backup's `.stx` boots straight out of the dump. If injection is
unavailable (no greaseweazle) or fails, it degrades to the sector-only STX with a loud
`sector-only` warning rather than losing the dump — the `.scp` is never at risk.

**The fix — convert the flux with Aufit, which writes full track images.** `gw/aufit.sh
<flux.scp>` opens Aufit (a Windows/.NET GUI, run under Wine) on the flux; load it, accept
the weak/fuzzy sectors on the protection band, and Export → Pasti. Aufit writes track flags
`0x61` with a real ~6 KB track image *and* the 1024-byte fuzzy mask per protected track, so
the Copylock's raw READ TRACK is satisfied. Confirmed on Wonder Boy disk 1: the Aufit STX
boots in Hatari with **zero** `no track image` warnings, where the hxcfe STX of the same
flux black-screened. Aufit is interactive by design (resolving weak bits wants a human), and
its WPF GUI needs a real desktop session — launching it from a headless/background shell
fails at graphics init. Alternatively, when a known-good Pasti dump of the same disk exists,
verify your dump against it sector-by-sector and play on that file.

**The automated fix — `gw/scp_to_stx.sh <flux.scp> [out.stx]`.** Replaces the manual Aufit
GUI step, fully offline (hxcfe + the greaseweazle Python library; no Greaseweazle hardware).
It runs hxcfe for the sectors/fuzzy mask, then decodes each track's flux to the WD1772 READ
TRACK byte stream and splices it in as a Pasti track-image sub-record, flipping every track
flag `0x01 → 0x61`; hxcfe's sector data and fuzzy mask are left byte-for-byte untouched.
Confirmed on Wonder Boy disk 1: matches Aufit's structure and boots in Hatari with **zero**
`no track image` warnings. `gw/test_scp_to_stx.sh` pins this — but its injection differential
and boot check need a local flux fixture (`dumps/wb_disk1/wb_disk1.scp`), and `dumps/` is
git-ignored, so on a fresh checkout the test **SKIPs**: there is no committed regression guard
for the injection until you dump that disk locally.

Hatari is launched with the same machine settings as `tools/hatari_run.sh` — 1 MiB ST, RGB
monitor, low-res TOS — using `tools/hatari/TOS104US.img`. `TOS_IMG` overrides the ROM in
both, though a Quick Action inherits almost no environment, so in practice that override is
for the command line. The emulator is `nohup`'d away from the caller: a Quick Action that
waits on an emulator would hang Finder until you quit it. The action still waits one second
before returning, long enough to notice a Hatari that dies during startup — otherwise a bad
ROM or a corrupt image reports success and opens no window.

A Quick Action has no terminal, so failures raise a Notification Center banner while every
outcome, success included, is appended to `~/Library/Logs/AtariQuickActions.log`. Hatari's
own console output lands in that same file, so a game that refuses to boot leaves its
complaint right under the launch line. Check the log whenever a notification is too terse.

### Quirks

- **The menu items show up on every file.** `NSSendFileTypes` filters by UTI, and `.st`,
  `.stx` and `.msa` have none registered on macOS — they resolve to per-machine `dyn.*`
  types that cannot be named in a plist. The bundles therefore accept `public.item` and the
  scripts reject the wrong extension with a notification. Hide the ones you do not want in
  System Settings → General → Login Items & Extensions → Finder extensions.
- **First run may prompt.** The scripts are unsigned and reach outside the sandbox, so
  macOS may ask once for permission to control Finder or to access the volume the images
  live on. Approve it once; it is remembered.
- Both bundles run headlessly for testing, which is how they were verified:
  `automator -i <file> ~/Library/Services/"Run in Hatari.workflow"`.

## Writing a disk back

`write_disk.sh <image>` writes a floppy from a `.st`, `.scp` or `.stx`. **It erases
the disk in the drive**, so it prints what it is about to do and waits for a typed
`y`. `--yes` skips that for scripting; with no terminal available it refuses rather
than writing unattended.

```bash
./write_disk.sh dumps/dungeon-master/dungeon-master.scp   # flux write of the gold master
./write_disk.sh game.stx                                  # .stx: flux route by default
./write_disk.sh plain.st                                  # verified sector write
./write_disk.sh plain.stx --sectors                       # unprotected .stx, verified
```

| Input | Route | Verify |
| --- | --- | --- |
| `.st` | sector write (uses `--format`) | gw reads every track back |
| `.scp` | flux write | none available |
| `.stx` | flux by default; `--sectors` converts to `.st` first | depends on route |

Converted intermediates go to a temp directory that is cleaned up on exit; `--keep`
puts them next to the input image instead (refusing to overwrite anything already
there — in a `dumps/<name>/` directory that would be the `.scp` gold master).

**The `.stx` route is checked less strictly than the `.scp` one.** Converting *from*
an SCP, hxcfe reports a track-generation line per track, so a flux-less input is
caught exactly. An STX gives no such per-track signal, so the converted output is
only checked for a plausible size — enough to catch a truncated STX, but a subtly
corrupt one can still pass. Writing the `.scp` gold master avoids the question.

### What verify actually does

From gw 1.23's `tools/write.py`, verify is skipped when:

```python
no_verify = (args.no_verify
             or not isinstance(track, MasterTrack)
             or (verify := track.verify) is None)
```

An SCP yields raw `Flux` objects, not `MasterTrack`s, so **on the flux route verify is
unavailable rather than disabled**. gw counts the track as written, skips the
read-back, and reports `No tracks verified (Reason: Verify unavailable)`. This is not
an error — and `--retries` never fires, because the retry loop breaks immediately.

Precisely: verify is unavailable on the flux route *because no `--format` is passed*.
A format is what makes gw build `MasterTrack`s carrying a verify model. Handing
`--format` to a flux write would make gw decode the image and verify it — a different
operation from reproducing the recorded waveform — which is why `write_disk.sh`
rejects `--format` on the flux route rather than quietly ignoring it.

Passing `--no-verify` there would only change the printed reason to "disabled", so
`write_disk.sh` does not pass it, and prints this instead:

```
Flux write: no sector verify - gw will report 'Verify unavailable'.
Test the disk in the machine, or re-read it with backup_disk.sh and compare.
```

On the sector route verify is real: every track is read back and compared, and gw
retries a failing track (default 3 times).

### Protection and a rewrite — better than expected

A flux write is the best reproduction available, but it is not the original disk:
weak/fuzzy bits get re-recorded as whatever the flux happened to say instead of as
genuinely unstable magnetisation, long tracks and tight inter-sector gaps depend on
your drive's exact rotation speed, and index alignment shifts. The textbook
expectation is that a protected game fails its own check after a rewrite.

**In practice it can survive — tested.** Wonder Boy in Monsterland disk 1 (Rob Northen
Copylock: a 12-sector band with weak bits on cylinders 0–4) was written back from its
`.scp` gold master with `write_disk.sh dumps/wb_disk1/wb_disk1.scp --tracks c=0-79:h=0`
and **booted and played on a real Atari ST past level 2, no error**. The flux write
reproduced the non-standard sector IDs, the track timing and the gap structure — the
structural parts of the protection — faithfully enough to pass. So write the flux and
just try it: some Copylock variants lean on layout/timing (which a flux write keeps)
rather than purely on non-reproducible weak bits, and the outcome is disk- and
drive-specific. For an unprotected disk prefer `--sectors`, because it is verified.

Write the original `dumps/<name>/<name>.scp` gold master rather than round-tripping
an STX. Every conversion is an interpretation; the SCP is the only artifact that
recorded what the drive actually saw.

**Media**: ST 720K disks are double density. Do not write to an HD disk with the hole
taped over — the coercivity is wrong and it will read back unreliably.

## Layout

`gw_lib.sh` holds what both scripts share (tool paths, logging, preflight, the hxcfe
wrapper). It is unrelated to `qa_lib.sh`, which serves the Finder Quick Actions.
`test_backup_disk.sh` and `test_write_disk.sh` are no-hardware smoke tests — they
stub `gw` and never touch the drive.

## Note

`dumps/` is git-ignored — flux images are tens of MB each and do not belong in this
repository. Archive them somewhere with real backups.