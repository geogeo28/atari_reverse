#!/usr/bin/env bash
#
# Atari ST floppy backup via Greaseweazle.
#
# The disk is spun exactly once: a multi-revolution raw flux read produces the SCP
# gold master. Every other artifact (STX, ST) is derived offline from that SCP, so
# fragile media is never re-read just to make another file format.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
# shellcheck source=gw_lib.sh
source "$SCRIPT_DIR/gw_lib.sh"

# Pasti/STX files begin with "RSY\0"; hxcfe can exit 0 after a soft failure, so the
# magic is checked as well as the exit status.
readonly STX_MAGIC="RSY"

# 5 revolutions is the preservation-community standard: enough passes to out-vote
# a bad read on any one revolution without an unreasonably long spin.
readonly DEFAULT_REVS=5
readonly DEFAULT_RETRIES=3       # gw's own default
readonly DEFAULT_SEEK_RETRIES=0  # gw's own default

readonly RESCUE_REVS=8
readonly RESCUE_RETRIES=8
readonly RESCUE_SEEK_RETRIES=3

readonly DUMPS_ROOT="$SCRIPT_DIR/dumps"

disk_name=""
drive="$DEFAULT_DRIVE"
device=""            # empty = let gw auto-detect the serial port
format="$DEFAULT_FORMAT"
tracks=""
revs="$DEFAULT_REVS"
retries="$DEFAULT_RETRIES"
seek_retries="$DEFAULT_SEEK_RETRIES"
revs_set=0           # an explicit --revs must survive --rescue
rescue=0
protected=0
force=0
preflight_only=0
convert_only=""
verify_result="not run"

usage() {
    cat <<EOF
Usage: $(basename "$0") <disk-name> [options]
       $(basename "$0") --convert-only <file.scp>

Reads an Atari ST floppy to a raw SCP flux gold master, then derives an STX
(Hatari, protection-aware) and — for unprotected disks — a verified .st image.

Options:
  --drive DRIVE     drive to read (default: $DEFAULT_DRIVE)
  --device DEV      serial port (default: gw auto-detects)
  --format FMT      disk format for verification/decode (default: $DEFAULT_FORMAT)
                    others: atarist.360 atarist.400 atarist.440 atarist.800 atarist.880
  --revs N          revolutions per track (default: $DEFAULT_REVS)
  --tracks TSPEC    restrict tracks, e.g. 'c=0-79:h=0-1'
  --rescue          damaged-disk mode: $RESCUE_REVS revs, $RESCUE_RETRIES retries, $RESCUE_SEEK_RETRIES seek-retries
  --protected       copy-protected disk: raw flux + STX only, no .st decode
  --force           overwrite an existing dump directory
  --preflight       check tools and device, then exit without touching the drive
  --convert-only F  convert an existing .scp to .stx and exit (no hardware needed)
  -h, --help        this help
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -h|--help)      usage; exit 0 ;;
            --drive)        require_value --drive "${2-}"; drive="$2"; shift 2 ;;
            --device)       require_value --device "${2-}"; device="$2"; shift 2 ;;
            --format)       require_value --format "${2-}"; format="$2"; shift 2 ;;
            --revs)         require_uint --revs "${2-}"; revs="$2"; revs_set=1; shift 2 ;;
            --tracks)       require_value --tracks "${2-}"; tracks="$2"; shift 2 ;;
            --convert-only) require_value --convert-only "${2-}"; convert_only="$2"; shift 2 ;;
            --preflight)    preflight_only=1; shift ;;
            --rescue)       rescue=1; shift ;;
            --protected)    protected=1; shift ;;
            --force)        force=1; shift ;;
            -*)             die "unknown option '$1' (try --help)" ;;
            *)
                [ -z "$disk_name" ] || die "unexpected extra argument '$1'"
                disk_name="$1"; shift ;;
        esac
    done

    if [ -n "$convert_only" ]; then
        [ -z "$disk_name" ] || die "--convert-only takes no disk name"
        return
    fi
    if [ "$preflight_only" -eq 1 ]; then
        return
    fi

    [ -n "$disk_name" ] || { usage >&2; die "a disk name is required"; }
    # The name becomes a directory and a filename stem.
    case "$disk_name" in
        */*|.*) die "disk name must not contain '/' or start with '.'" ;;
    esac

    # Rescue raises the defaults but must not override what the user asked for.
    if [ "$rescue" -eq 1 ]; then
        if [ "$revs_set" -eq 0 ]; then
            revs="$RESCUE_REVS"
        fi
        retries="$RESCUE_RETRIES"
        seek_retries="$RESCUE_SEEK_RETRIES"
    fi
}

read_flux() {
    local scp="$1"
    local -a cmd=("$GW_BIN" read --raw --revs "$revs" --drive "$drive")

    if [ -n "$device" ]; then
        cmd+=(--device "$device")
    fi
    if [ -n "$tracks" ]; then
        cmd+=(--tracks "$tracks")
    fi
    # Without --format gw performs no decode, so its retry loop never runs; a
    # protected disk therefore relies on revolutions alone. With --format, retry
    # passes are appended to the raw stream, enriching the gold master.
    if [ "$protected" -eq 0 ]; then
        cmd+=(--format "$format" --retries "$retries" --seek-retries "$seek_retries")
    fi
    cmd+=("$scp")

    log "--- Reading flux: ${revs} revolutions, drive $drive ---"
    log "\$ ${cmd[*]}"
    run_logged "${cmd[@]}" || die "gw read failed - see $log_file"
    [ -s "$scp" ] || die "gw read produced no flux data: $scp"
}

convert_scp_to_stx() {
    local scp="$1" stx="$2"

    log "--- Converting SCP -> STX ---"
    hxcfe_convert "$scp" "$stx" "$HXCFE_STX_MODULE" 1
    [ "$(head -c ${#STX_MAGIC} "$stx")" = "$STX_MAGIC" ] \
        || die "output is not a valid STX file (missing '$STX_MAGIC' signature): $stx"
    log "STX written: $stx ($HXCFE_TRACKS_CONVERTED tracks converted)"
}

# Decodes the gold master to a sector image. Returns non-zero when the disk does not
# fully verify, which is expected (not an error) for protected media.
convert_scp_to_st() {
    local scp="$1" st="$2" output status=0

    log "--- Decoding SCP -> ST (format $format) ---"
    output="$("$GW_BIN" convert --format "$format" "$scp" "$st" 2>&1)" || status=$?
    if [ -n "$log_file" ]; then
        echo "$output" >>"$log_file"
    fi
    echo "$output"

    if [ "$status" -ne 0 ]; then
        verify_result="gw convert failed"
        log "WARNING: gw convert failed - no .st image produced."
        rm -f "$st"
        return 1
    fi
    # gw prints e.g. "Found 1440 sectors of 1440 (100%)"; anything short of every
    # sector means the sector image is incomplete.
    local found
    found="$(grep -o 'Found [0-9]* sectors of [0-9]* ([0-9]*%)' <<<"$output" | tail -1)"
    verify_result="${found:-no verification summary reported}"
    grep -q '(100%)' <<<"$found" || return 1
    return 0
}

print_summary() {
    local dir="$1" st_status="$2"
    log ""
    log "=== Summary: $disk_name ==="
    local f
    for f in "$dir/$disk_name".*; do
        if [ -f "$f" ]; then
            log "  $(basename "$f")  $(wc -c <"$f" | tr -d ' ') bytes"
        fi
    done
    log ""
    if [ "$protected" -eq 1 ]; then
        log "  Sector verification: SKIPPED (--protected: flux + STX only)."
    else
        log "  Sector verification: $verify_result"
        if [ "$st_status" -ne 0 ]; then
            log "  Bad/unreadable sectors were found. The .st image is unreliable."
            log "  If the disk is copy-protected this is EXPECTED - use the STX with Hatari."
            log "  If it should be a plain disk, re-run with --rescue and clean the drive heads."
            log "  Tracks with missing sectors are marked 'X' in the map above (see $log_file)."
        else
            log "  All sectors read cleanly."
        fi
    fi
    log ""
    log "  Keep the .scp forever - it is the only lossless record of the disk."
    log "  Full log: $log_file"
}

# Standalone SCP -> STX, used to exercise the conversion leg without a drive.
run_convert_only() {
    local scp="$convert_only" parent base
    [ -f "$scp" ] || die "no such file: $scp"
    check_tools "$HXCFE_STX_MODULE"
    # Strip the extension from the basename only: "%.*" on a full path would cut at a
    # dot in a parent directory and write the STX outside the dump directory.
    parent="$(dirname "$scp")"
    base="$(basename "$scp")"
    convert_scp_to_stx "$scp" "$parent/${base%.*}.stx"
}

main() {
    parse_args "$@"

    if [ -n "$convert_only" ]; then
        run_convert_only
        return
    fi
    if [ "$preflight_only" -eq 1 ]; then
        preflight "$HXCFE_STX_MODULE"
        echo "Preflight OK - tools present and Greaseweazle detected."
        return
    fi

    local dir="$DUMPS_ROOT/$disk_name"
    if [ -e "$dir" ] && [ "$force" -eq 0 ]; then
        die "dump directory already exists: $dir"$'\n'"Pass --force to overwrite it."
    fi

    # Checked before the directory exists: a failed preflight must not leave a dump
    # directory behind that the next attempt would refuse as "already exists".
    local device_info
    device_info="$(preflight "$HXCFE_STX_MODULE")"

    mkdir -p "$dir"

    local scp="$dir/$disk_name.scp"
    local stx="$dir/$disk_name.stx"
    local st="$dir/$disk_name.st"

    # A reused (--force) directory must not keep the previous run's artifacts: a stale
    # .stx would pass the sanity checks even if this run converted nothing.
    rm -f "$scp" "$stx" "$st" "$dir/read.log"

    log_file="$dir/read.log"
    : >"$log_file"

    log_preflight "$device_info"
    read_flux "$scp"
    convert_scp_to_stx "$scp" "$stx"

    local st_status=0
    if [ "$protected" -eq 1 ]; then
        log "--- Skipping .st decode (--protected) ---"
    else
        convert_scp_to_st "$scp" "$st" || st_status=$?
    fi

    print_summary "$dir" "$st_status"
}

main "$@"