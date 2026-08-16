#!/usr/bin/env bash
#
# Convert an Atari ST GreaseWeazle flux dump (.scp) into a bootable, protection-preserving
# Pasti STX -- replacing the manual Aufit GUI step.
#
# hxcfe's ATARIST_STX conversion writes a *sector-only* STX (track flag 0x01): it omits the
# raw track image a WD1772 READ TRACK returns. Copy-protected games (Rob Northen Copylock)
# issue READ TRACK on their protection tracks; with no track image Hatari logs
# "fdc stx : no track image for read track ..." and the game hangs. This script runs hxcfe,
# then post-processes its STX to decode each track's flux into that READ TRACK byte stream
# and splice it in as a Pasti track-image sub-record (flag 0x01 -> 0x61). Nothing about the
# sector data or fuzzy/weak-bit mask hxcfe already wrote is touched.
#
# Offline and non-destructive: no GreaseWeazle hardware is used and no input is modified.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# gw_lib.sh gives us the hxcfe wrapper, hxcfe_convert, die and the module/tool-path names.
source "$SCRIPT_DIR/gw_lib.sh"

readonly WORKER="$SCRIPT_DIR/inject_track_images.py"
# The greaseweazle flux decoder + ibm MFM codec live in this conda env's Python.
readonly PYTHON="/Users/geogeo/miniconda3/envs/atari_reverse/bin/python"

usage() {
    cat >&2 <<EOF
usage: $(basename "$0") <flux.scp> [out.stx] [--force]

Converts a GreaseWeazle .scp flux dump into a bootable, protection-preserving Pasti .stx.
  <flux.scp>   input flux dump (SCP)
  [out.stx]    output path (default: <flux>.stx next to the input)
  --force      overwrite an existing output file
EOF
    exit 2
}

# This is a pure offline conversion: it uses hxcfe and the greaseweazle Python *library*,
# never the gw hardware CLI. So it runs its own preflight instead of gw_lib's check_tools,
# which hard-requires the gw binary -- that would wrongly refuse on a machine with hxcfe +
# the library but no Greaseweazle attached. (check_tools stays as-is for the hardware scripts.)
check_offline_tools() {
    [ -x "$HXCFE_BIN" ] || die "hxcfe not found or not executable: $HXCFE_BIN"
    [ -d "$HXCFE_LIB_DIR" ] || die "hxcfe library directory missing: $HXCFE_LIB_DIR"
    # Listing the modules proves hxcfe loads its shared libraries and has the STX writer.
    hxcfe -modulelist 2>/dev/null | grep -q "^${HXCFE_STX_MODULE};" \
        || die "hxcfe runs but has no $HXCFE_STX_MODULE module (check DYLD_LIBRARY_PATH=$HXCFE_LIB_DIR)"

    [ -f "$WORKER" ] || die "worker not found: $WORKER"
    [ -x "$PYTHON" ] || die "python not found or not executable: $PYTHON"
    "$PYTHON" -c "import greaseweazle.image.scp, greaseweazle.codec.ibm.ibm" 2>/dev/null \
        || die "greaseweazle not importable by $PYTHON (need the atari_reverse env)"
}

flux=""
out=""
force=0
while [ $# -gt 0 ]; do
    case "$1" in
        --force) force=1 ;;
        -h|--help) usage ;;
        -*) die "unknown option: $1" ;;
        *) if [ -z "$flux" ]; then flux="$1"; elif [ -z "$out" ]; then out="$1"; else die "too many arguments"; fi ;;
    esac
    shift
done

[ -n "$flux" ] || usage
[ -f "$flux" ] || die "no such file: $flux"
[ "$(lowercase_extension "$flux")" = "scp" ] || die "input must be a .scp flux dump: $flux"

# Default the output next to the input, swapping .scp for .stx.
if [ -z "$out" ]; then
    out="${flux%.*}.stx"
fi
if [ -e "$out" ] && [ "$force" -ne 1 ]; then
    die "output exists (use --force to overwrite): $out"
fi

check_offline_tools

# hxcfe writes the sector-only STX to a temp file; the worker reads it plus the flux and
# writes the final imaged STX. Clean the temp up on any exit.
tmp_dir="$(mktemp -d -t scp_to_stx)"
tmp_stx="$tmp_dir/sector_only.stx"
trap 'rm -rf "$tmp_dir"' EXIT

echo "Converting flux -> sector-only STX (hxcfe)..."
hxcfe_convert "$flux" "$tmp_stx" "$HXCFE_STX_MODULE" 1 >/dev/null

echo "Injecting WD1772 track images from flux..."
"$PYTHON" "$WORKER" "$tmp_stx" "$flux" "$out"

echo "Done: $out"
