# Atari ST floppy backup (Greaseweazle)

Backs up Atari ST floppies to preservation-grade images using a Greaseweazle V4.1
and the HxC command-line converter.

## Pipeline

The disk is spun **once**. Everything else is derived offline from that read, so a
fragile disk is never re-read just to produce another file format.

```
floppy ──gw read --raw──> .scp  (flux gold master, keep forever)
                           ├──hxcfe──> .stx  (Pasti; protection-aware, for Hatari)
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

## Note

`dumps/` is git-ignored — flux images are tens of MB each and do not belong in this
repository. Archive them somewhere with real backups.