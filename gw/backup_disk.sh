#!/usr/bin/env bash
#
# Atari ST floppy backup via Greaseweazle.
#
# The disk is spun exactly once: a multi-revolution raw flux read produces the SCP
# gold master. Every other artifact (STX, ST) is derived offline from that SCP, so
# fragile media is never re-read just to make another file format.

set -euo pipefail

readonly GW_BIN="/Users/geogeo/miniconda3/envs/atari_reverse/bin/gw"
readonly HXCFE_BIN="/Users/geogeo/opt/hxcfe_cmdline/App/hxcfe"
readonly HXCFE_LIB_DIR="/Users/geogeo/opt/hxcfe_cmdline/Frameworks"

readonly HXCFE_STX_MODULE="ATARIST_STX"
# Pasti/STX files begin with "RSY\0"; hxcfe can exit 0 after a soft failure, so the
# magic is checked as well as the exit status.
readonly STX_MAGIC="RSY"
# hxcfe also exits 0 when it converts *nothing*: it writes a valid-looking header and
# logs one "not allocated" line per track side. A real conversion logs a track
# generation line per track, so that count - not the exit status - decides success.
readonly HXCFE_TRACK_MARKER='Revolution [0-9]* track generation'
readonly HXCFE_UNALLOCATED_MARKER='not allocated'

readonly DEFAULT_FORMAT="atarist.720"
readonly DEFAULT_DRIVE="A"

# 5 revolutions is the preservation-community standard: enough passes to out-vote
# a bad read on any one revolution without an unreasonably long spin.
readonly DEFAULT_REVS=5
readonly DEFAULT_RETRIES=3       # gw's own default
readonly DEFAULT_SEEK_RETRIES=0  # gw's own default

readonly RESCUE_REVS=8
readonly RESCUE_RETRIES=8
readonly RESCUE_SEEK_RETRIES=3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
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
log_file=""
verify_result="not run"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

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

# Values are taken positionally, so a forgotten value would silently swallow the next
# flag (--revs --protected). Both checks reject that instead of acting on nonsense.
require_value() {
    local flag="$1" value="${2-}"
    case "$value" in
        ""|-*) die "$flag needs a value (got '${value}')" ;;
    esac
}

require_uint() {
    local flag="$1" value="${2-}"
    [[ "$value" =~ ^[0-9]+$ ]] || die "$flag needs a non-negative integer (got '${value}')"
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

# Log to the dump directory when there is one; --convert-only self-tests have none.
log() {
    if [ -n "$log_file" ]; then
        # A failing tee must not abort an otherwise successful backup.
        echo "$*" | tee -a "$log_file" || true
    else
        echo "$*"
    fi
}

# Runs a command with its output shown live and appended to the log, returning the
# command's own exit status rather than tee's.
run_logged() {
    local status
    if [ -n "$log_file" ]; then
        "$@" 2>&1 | tee -a "$log_file"
        status=${PIPESTATUS[0]}
    else
        "$@" 2>&1
        status=$?
    fi
    return "$status"
}

hxcfe() {
    DYLD_LIBRARY_PATH="$HXCFE_LIB_DIR" "$HXCFE_BIN" "$@"
}

check_tools() {
    [ -x "$GW_BIN" ] || die "Greaseweazle host tool not found or not executable: $GW_BIN"
    [ -x "$HXCFE_BIN" ] || die "hxcfe not found or not executable: $HXCFE_BIN"
    [ -d "$HXCFE_LIB_DIR" ] || die "hxcfe library directory missing: $HXCFE_LIB_DIR"

    # Proves hxcfe actually loads its shared libraries and carries the STX writer,
    # which a bare existence check would not.
    hxcfe -modulelist 2>/dev/null | grep -q "^${HXCFE_STX_MODULE};" \
        || die "hxcfe runs but has no $HXCFE_STX_MODULE module (check DYLD_LIBRARY_PATH=$HXCFE_LIB_DIR)"
}

check_device() {
    local info
    local -a cmd=("$GW_BIN" info)
    if [ -n "$device" ]; then
        cmd+=(--device "$device")
    fi
    info="$("${cmd[@]}" 2>&1)" \
        || die "'gw info' failed - is the Greaseweazle plugged in?"$'\n'"$info"
    grep -q "Model:" <<<"$info" \
        || die "'gw info' did not report a device - check the USB cable/port."$'\n'"$info"
    echo "$info"
}

# Echoes the device info so the caller can log it once a log file exists.
preflight() {
    check_tools
    check_device
}

log_preflight() {
    local info="$1"
    log "--- Preflight ---"
    log "$info"
    log "gw:    $GW_BIN"
    log "hxcfe: $HXCFE_BIN"
    log ""
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
    local scp="$1" stx="$2" output status=0

    log "--- Converting SCP -> STX ---"
    output="$(hxcfe -finput:"$scp" -conv:"$HXCFE_STX_MODULE" -foutput:"$stx" 2>&1)" || status=$?
    if [ -n "$log_file" ]; then
        echo "$output" >>"$log_file"
    fi
    echo "$output"

    [ "$status" -eq 0 ] || die "hxcfe failed converting $scp -> $stx"
    [ -s "$stx" ] || die "hxcfe reported success but wrote no STX data: $stx"
    [ "$(head -c ${#STX_MAGIC} "$stx")" = "$STX_MAGIC" ] \
        || die "output is not a valid STX file (missing '$STX_MAGIC' signature): $stx"

    local generated unallocated
    generated="$(grep -c "$HXCFE_TRACK_MARKER" <<<"$output" || true)"
    unallocated="$(grep -c "$HXCFE_UNALLOCATED_MARKER" <<<"$output" || true)"
    # Counting generated tracks rather than checking a file size keeps partial
    # (--tracks) dumps valid while still catching a header-only STX.
    [ "$generated" -gt 0 ] \
        || die "hxcfe converted no tracks ($unallocated unallocated) - the SCP holds no flux data: $scp"
    if [ "$unallocated" -gt 0 ]; then
        log "WARNING: $unallocated track side(s) could not be converted - the STX is incomplete."
    fi
    log "STX written: $stx ($generated tracks converted)"
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
    check_tools
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
        preflight
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
    device_info="$(preflight)"

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