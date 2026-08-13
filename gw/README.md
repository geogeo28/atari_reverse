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

## Note

`dumps/` is git-ignored — flux images are tens of MB each and do not belong in this
repository. Archive them somewhere with real backups.