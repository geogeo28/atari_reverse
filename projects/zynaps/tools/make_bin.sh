#!/usr/bin/env bash
# Regenerate projects/zynaps/bin/ — the whole directory is gitignored, so this script is the only
# record of how it was made. From the read-only gold master gw/dumps/zynaps/zynaps.st it produces:
#
#   <outdir>/zynaps.st     the master with its BPB FAT count patched 1 -> 2 (see below)
#   <outdir>/disk/         every file on the volume, extracted by tools/st_extract.py
#   <outdir>/ZYNAPS17.PRG  a copy of disk/AUTO/ZYNAPS17.PRG, the binary the project analyses
#
# WHY THE PATCH. The disk really carries two FATs of three sectors each, so its root directory
# begins at sector 1 + 2*3 = 7 — but the boot sector's BPB says one FAT, which puts the root at
# sector 4, where there is nothing. Reading it needs the corrected count; `st_extract.py --nfats 2`
# supplies it without touching the image, and this script instead writes the corrected byte into
# its copy so that EVERY other tool (Hatari, a mounter, an emulator) sees a mountable volume too.
# The gold master itself is never modified.
#
# WHY NOT stx_extract --to-st. gw/dumps/zynaps/zynaps.stx re-decodes to an image that differs from
# gw/dumps/zynaps/zynaps.st across cylinders 77-79 (sectors 770-799, past the data this disk uses),
# so the .st dump is the master here and the byte-for-byte source of what bin/ has always held.
#
# Usage: bash projects/zynaps/tools/make_bin.sh [OUTDIR]     # default: projects/zynaps/bin
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MASTER_ST="$REPO/gw/dumps/zynaps/zynaps.st"
ST_EXTRACT="$REPO/tools/st_extract.py"
OUT_DIR="${1:-$REPO/projects/zynaps/bin}"

# BPB byte 16 is the FAT count (DOS layout; see tools/st_extract.py BPB_FAT_COUNT).
BPB_FAT_COUNT_OFFSET=16
MASTER_FAT_COUNT=1          # what the dump's BPB wrongly claims
ACTUAL_FAT_COUNT=2          # what the volume really holds

GAME_PRG_ON_DISK="AUTO/ZYNAPS17.PRG"
EXPECTED_FILES=63
EXPECTED_BYTES=326382

IMAGE="$OUT_DIR/zynaps.st"
DISK_DIR="$OUT_DIR/disk"

mkdir -p "$OUT_DIR"
rm -rf "$DISK_DIR"
cp "$MASTER_ST" "$IMAGE"

python3 - "$IMAGE" "$BPB_FAT_COUNT_OFFSET" "$MASTER_FAT_COUNT" "$ACTUAL_FAT_COUNT" <<'PY'
"""Patch one BPB byte in place, refusing unless it still holds the value the master is known to."""
import sys

path, offset, expected, corrected = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
with open(path, "r+b") as image:
    image.seek(offset)
    found = image.read(1)[0]
    if found != expected:
        sys.exit("%s: BPB byte %d is %d, expected the master's %d — refusing to patch"
                 % (path, offset, found, expected))
    image.seek(offset)
    image.write(bytes([corrected]))
PY

summary="$(python3 "$ST_EXTRACT" "$IMAGE" -o "$DISK_DIR" | tail -1)"
echo "$summary"
case "$summary" in
    "extracted $EXPECTED_FILES files, $EXPECTED_BYTES bytes"*) ;;
    *) echo "make_bin.sh: expected $EXPECTED_FILES files / $EXPECTED_BYTES bytes" >&2; exit 1 ;;
esac

cp "$DISK_DIR/$GAME_PRG_ON_DISK" "$OUT_DIR/$(basename "$GAME_PRG_ON_DISK")"
echo "regenerated $OUT_DIR from $MASTER_ST"
