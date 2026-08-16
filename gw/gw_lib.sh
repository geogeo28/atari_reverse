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

# The track-image injection worker (inject_track_images.py) sits alongside this library, and
# needs the greaseweazle flux decoder + ibm MFM codec that live in the atari_reverse env's
# Python. Resolving the worker off this file's own directory keeps it findable from any caller.
GW_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly GW_LIB_DIR
readonly GW_PYTHON="/Users/geogeo/miniconda3/envs/atari_reverse/bin/python"
readonly INJECT_WORKER="$GW_LIB_DIR/inject_track_images.py"

# Pasti/STX files begin with "RSY\0"; hxcfe can exit 0 after a soft failure, so the magic is
# checked as well as the exit status before an STX is trusted.
readonly STX_MAGIC="RSY"

# Hatari saves 'write sector'/'write track' changes to a <name>.wd1772 sidecar beside the STX.
# The sidecar is bound to the exact STX it was captured from; regenerating the STX makes it
# stale and Hatari then refuses to boot with "Error restoring STX save buffer". So a fresh STX
# must delete any sidecar next to it (Hatari replaces the .stx extension, hence "${stx%.*}").
readonly HATARI_STX_SIDECAR_EXT="wd1772"

# hxcfe exits 0 even when it converts *nothing*: it writes a valid-looking header and
# logs one "not allocated" line per track side. A real conversion logs a track
# generation line per track, so that count - not the exit status - decides success.
readonly HXCFE_TRACK_MARKER='Revolution [0-9]* track generation'
readonly HXCFE_UNALLOCATED_MARKER='not allocated'

readonly DEFAULT_FORMAT="atarist.720"
readonly DEFAULT_DRIVE="A"

# Standard Atari ST sector-image geometries, named by their byte size (bytes =
# sectors * 512). A .st file's byte size fixes its on-disk geometry, so the write path
# infers the format from the size rather than defaulting blindly: the wrong geometry
# lays down a track layout TOS reads as an EMPTY disk, with no error to warn you.
# Single-sided: 360/400/440. Double-sided: 720/800/880.
readonly ST_SIZE_360=368640    # atarist.360 =  720 sectors
readonly ST_SIZE_400=409600    # atarist.400 =  800 sectors
readonly ST_SIZE_440=450560    # atarist.440 =  880 sectors
readonly ST_SIZE_720=737280    # atarist.720 = 1440 sectors
readonly ST_SIZE_800=819200    # atarist.800 = 1600 sectors
readonly ST_SIZE_880=901120    # atarist.880 = 1760 sectors

# One authoritative "<bytes>:<format>" table, built from the size constants so the
# numbers live in exactly one place; the lookups below iterate it in either direction.
readonly ST_GEOMETRY_TABLE="\
$ST_SIZE_360:atarist.360
$ST_SIZE_400:atarist.400
$ST_SIZE_440:atarist.440
$ST_SIZE_720:atarist.720
$ST_SIZE_800:atarist.800
$ST_SIZE_880:atarist.880"

# Echo the atarist.* format for a byte size, or nothing if the size is not a known ST
# geometry.
st_format_for_size() {
    local size fmt
    while IFS=: read -r size fmt; do
        if [ "$size" = "$1" ]; then printf '%s' "$fmt"; return; fi
    done <<<"$ST_GEOMETRY_TABLE"
}

# Echo the expected byte size for an atarist.* format, or nothing when the format has
# no single fixed geometry (a custom format the user knows better than we do).
st_size_for_format() {
    local size fmt
    while IFS=: read -r size fmt; do
        if [ "$fmt" = "$1" ]; then printf '%s' "$size"; return; fi
    done <<<"$ST_GEOMETRY_TABLE"
}

# The known ST sizes with their formats, as one line, for error messages.
st_known_sizes() {
    local size fmt out=""
    while IFS=: read -r size fmt; do
        out+="${out:+, }$size ($fmt)"
    done <<<"$ST_GEOMETRY_TABLE"
    printf '%s' "$out"
}

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

# True when the greaseweazle Python library (the flux decoder the injection worker needs) is
# importable. Injection is optional: a caller that cannot import it falls back to sector-only.
greaseweazle_available() {
    "$GW_PYTHON" -c "import greaseweazle.image.scp, greaseweazle.codec.ibm.ibm" 2>/dev/null
}

# convert_scp_to_bootable_stx <scp> <stx>
# Convert an SCP flux dump into a bootable, protection-preserving STX.
#
# hxcfe writes a sector-only STX (track flag 0x01) that omits the raw track images a WD1772
# READ TRACK returns, so Copylock-protected games black-screen on it. This runs hxcfe, then
# splices the track images decoded from the flux into every track (flag 0x01 -> 0x61).
#
# Postcondition: on success <stx> is the bootable 0x61 image and the return is 0. If injection
# is unavailable (greaseweazle Python missing) or fails, <stx> is left as the valid sector-only
# 0x01 image hxcfe produced and the return is non-zero -- each caller decides whether that
# degraded result is fatal (scp_to_stx dies) or acceptable (backup_disk warns, keeps the dump).
# An outright hxcfe failure leaves no STX to fall back to and dies inside hxcfe_convert.
convert_scp_to_bootable_stx() {
    local scp="$1" stx="$2" tmp prev_exit_trap

    # hxcfe's stdout is verbose per-track spam; it is already appended to the log by
    # hxcfe_convert itself, so discard the terminal copy and keep progress on the log.
    hxcfe_convert "$scp" "$stx" "$HXCFE_STX_MODULE" 1 >/dev/null
    [ "$(head -c ${#STX_MAGIC} "$stx")" = "$STX_MAGIC" ] \
        || die "output is not a valid STX file (missing '$STX_MAGIC' signature): $stx"

    # This STX was just (re)written, so any Hatari write-back sidecar beside it is now stale;
    # leaving it would make Hatari abort on boot. Whether injection succeeds or not below, the
    # STX content differs from whatever the sidecar was saved against, so drop it here.
    rm -f "${stx%.*}.$HATARI_STX_SIDECAR_EXT"

    if ! greaseweazle_available; then
        log "WARNING: greaseweazle Python not available - STX is sector-only (0x01); protected games will not boot."
        return 1
    fi

    # Inject into a temp in the SAME directory as $stx so publishing the result is an atomic
    # same-filesystem rename: a crash or Ctrl-C mid-write can never leave a half-written boot
    # image at $stx (the file the user boots). A failed or partial worker write only ever
    # touches the temp, so the sector-only STX we keep as the fallback is safe until the rename.
    # An EXIT trap removes the temp if we are interrupted before the rename; it is saved and
    # restored around this block so a caller's own EXIT trap is left intact.
    prev_exit_trap="$(trap -p EXIT)"
    tmp="$(mktemp "$(dirname "$stx")/.inject.XXXXXX")"
    trap 'rm -f "$tmp"' EXIT
    if run_logged "$GW_PYTHON" "$INJECT_WORKER" "$stx" "$scp" "$tmp"; then
        mv "$tmp" "$stx"
        eval "${prev_exit_trap:-trap - EXIT}"
        log "STX track images injected: $stx (track flag 0x61)."
        log "  NOTE: this adds the track image a READ TRACK needs, but does NOT reliably"
        log "  reproduce a weak-bit Copylock. Boot-test it; if it black-screens, use gw/aufit.sh."
        return 0
    fi
    rm -f "$tmp"
    eval "${prev_exit_trap:-trap - EXIT}"
    log "WARNING: track-image injection failed - STX is sector-only (0x01); protected games will not boot."
    return 1
}
