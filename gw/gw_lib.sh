# Shared helpers for the Greaseweazle disk scripts (backup_disk.sh, write_disk.sh).
# Sourced, not executed.
#
# Distinct from qa_lib.sh, which serves the Finder Quick Actions (notifications and
# logging for scripts that have no terminal). Do not merge the two: this library
# talks to hardware and prints to a terminal.

# Sourcing twice would abort on the readonly declarations below.
if [ -n "${GW_LIB_SOURCED:-}" ]; then
    return 0
fi
GW_LIB_SOURCED=1

readonly GW_BIN="/Users/geogeo/miniconda3/envs/atari_reverse/bin/gw"
readonly HXCFE_BIN="/Users/geogeo/opt/hxcfe_cmdline/App/hxcfe"
readonly HXCFE_LIB_DIR="/Users/geogeo/opt/hxcfe_cmdline/Frameworks"

readonly HXCFE_STX_MODULE="ATARIST_STX"
readonly HXCFE_SCP_MODULE="SCP_FLUX_STREAM"
readonly HXCFE_ST_MODULE="ATARIST_ST"

# hxcfe exits 0 even when it converts *nothing*: it writes a valid-looking header and
# logs one "not allocated" line per track side. A real conversion logs a track
# generation line per track, so that count - not the exit status - decides success.
readonly HXCFE_TRACK_MARKER='Revolution [0-9]* track generation'
readonly HXCFE_UNALLOCATED_MARKER='not allocated'

readonly DEFAULT_FORMAT="atarist.720"
readonly DEFAULT_DRIVE="A"

# gw catches USB command errors, prints this and still exits 0 (write.py), so the
# transcript is the only place such a failure is visible.
readonly GW_COMMAND_FAILED_MARKER="Command Failed:"

log_file=""                  # set by a caller that wants a transcript
device=""                    # empty = let gw auto-detect; callers may override
HXCFE_TRACKS_CONVERTED=0     # tracks converted by the last hxcfe_convert call

die() {
    echo "ERROR: $*" >&2
    exit 1
}

# Log to the caller's log file when there is one, otherwise just to the terminal.
log() {
    if [ -n "$log_file" ]; then
        # A failing tee must not abort an otherwise successful operation.
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

# Extensions are compared lowercased so DISK.STX is treated like disk.stx.
lowercase_extension() {
    local base
    base="$(basename "$1")"
    printf '%s' "${base##*.}" | tr '[:upper:]' '[:lower:]'
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

# check_tools <required hxcfe module>...
check_tools() {
    [ -x "$GW_BIN" ] || die "Greaseweazle host tool not found or not executable: $GW_BIN"
    [ -x "$HXCFE_BIN" ] || die "hxcfe not found or not executable: $HXCFE_BIN"
    [ -d "$HXCFE_LIB_DIR" ] || die "hxcfe library directory missing: $HXCFE_LIB_DIR"

    # Listing the modules proves hxcfe actually loads its shared libraries, which a
    # bare existence check would not.
    local modules module
    modules="$(hxcfe -modulelist 2>/dev/null)" \
        || die "hxcfe failed to run (check DYLD_LIBRARY_PATH=$HXCFE_LIB_DIR)"
    for module in "$@"; do
        grep -q "^${module};" <<<"$modules" \
            || die "hxcfe runs but has no $module module (check DYLD_LIBRARY_PATH=$HXCFE_LIB_DIR)"
    done
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
# preflight <required hxcfe module>...
preflight() {
    check_tools "$@"
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

# hxcfe_convert <input> <output> <module> <input_is_flux>
# input_is_flux must be 1 only for flux (SCP) input - see the track-marker note below.
# Dies unless the conversion produced usable output; sets HXCFE_TRACKS_CONVERTED.
hxcfe_convert() {
    local input="$1" output_file="$2" module="$3" input_is_flux="$4" output status=0

    output="$(hxcfe -finput:"$input" -conv:"$module" -foutput:"$output_file" 2>&1)" || status=$?
    if [ -n "$log_file" ]; then
        echo "$output" >>"$log_file"
    fi
    echo "$output"

    [ "$status" -eq 0 ] || die "hxcfe failed converting $input -> $output_file"
    [ -s "$output_file" ] || die "hxcfe reported success but wrote no data: $output_file"

    local generated unallocated
    generated="$(grep -c "$HXCFE_TRACK_MARKER" <<<"$output" || true)"
    unallocated="$(grep -c "$HXCFE_UNALLOCATED_MARKER" <<<"$output" || true)"
    # The track-generation marker is printed by hxcfe's SCP *loader* as it turns
    # revolutions into tracks, so it only carries meaning when the input is flux.
    # Other loaders (STX, ST) never print it and must not be judged by it.
    # Counting tracks rather than checking a file size keeps partial (--tracks)
    # images valid while still catching a header-only SCP.
    if [ "$input_is_flux" -eq 1 ]; then
        [ "$generated" -gt 0 ] \
            || die "hxcfe converted no tracks ($unallocated unallocated) - no flux data in: $input"
    fi
    if [ "$unallocated" -gt 0 ]; then
        log "WARNING: $unallocated track side(s) could not be converted - the output is incomplete."
    fi
    HXCFE_TRACKS_CONVERTED="$generated"
}
