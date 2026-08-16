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
# gw_lib.sh gives us the hxcfe wrapper, the shared convert_scp_to_bootable_stx pipeline, die,
# and the module/tool-path names (INJECT_WORKER, GW_PYTHON included).
source "$SCRIPT_DIR/gw_lib.sh"

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

    # Injection is the whole point here, so its dependencies are hard requirements (unlike
    # backup_disk, which degrades to a sector-only STX when they are missing).
    [ -f "$INJECT_WORKER" ] || die "injection worker not found: $INJECT_WORKER"
    [ -x "$GW_PYTHON" ] || die "python not found or not executable: $GW_PYTHON"
    greaseweazle_available \
        || die "greaseweazle not importable by $GW_PYTHON (need the atari_reverse env)"
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

# The shared pipeline runs hxcfe then injects the track images, leaving a sector-only STX at
# $out if injection fails. Here injection failure is fatal (a bootable STX is the whole point),
# so surface it as an error while making clear what the leftover file is.
echo "Converting flux -> bootable STX (hxcfe + track-image injection)..."
if convert_scp_to_bootable_stx "$flux" "$out"; then
    echo "Done (bootable, track flag 0x61): $out"
else
    die "track-image injection failed; left a sector-only STX that will NOT boot protected games: $out"
fi
