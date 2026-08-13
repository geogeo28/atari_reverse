#!/usr/bin/env bash
#
# Write an Atari ST floppy from an image, via Greaseweazle.
#
# Two routes exist and they are not equivalent. A sector write (.st) is verified by
# gw reading each track back. A flux write (.scp) reproduces the recorded waveform,
# which is the only way protection has any chance of surviving - but gw cannot verify
# it, because a raw flux track carries no sector model to compare against.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
# shellcheck source=gw_lib.sh
source "$SCRIPT_DIR/gw_lib.sh"

readonly ROUTE_SECTOR="sector"
readonly ROUTE_FLUX="flux"
readonly CONFIRM_WORD="y"

# An STX carries no per-track marker hxcfe reports on, so the converted output is
# sanity-checked by size instead. Measured on this toolchain: a truncated 8-byte STX
# still yields a 225,814-byte SCP, while a real 720K disk yields ~46 MB and the
# smallest single-sided disk still runs to several MB. 1 MB sits well clear of both.
readonly MIN_CONVERTED_FLUX_BYTES=1048576
# Smallest sector image gw has a format for (atarist.360 = 40 cyl * 2 heads * 9 * 512).
readonly MIN_CONVERTED_SECTOR_BYTES=368640

image=""
drive="$DEFAULT_DRIVE"
device=""            # empty = let gw auto-detect the serial port
format="$DEFAULT_FORMAT"
format_set=""        # non-empty once --format is given explicitly
tracks=""
no_verify=0
sectors=0
keep=0
assume_yes=0

route=""             # ROUTE_SECTOR or ROUTE_FLUX, chosen by extension
write_source=""      # the file actually handed to gw (may be a conversion)
temp_dir=""

cleanup() {
    if [ -n "$temp_dir" ]; then
        rm -rf "$temp_dir"
    fi
}
trap cleanup EXIT

ensure_temp_dir() {
    if [ -z "$temp_dir" ]; then
        temp_dir="$(mktemp -d)"
    fi
}

usage() {
    cat <<EOF
Usage: $(basename "$0") <image> [options]

Writes a floppy in the Greaseweazle drive from a .st, .scp or .stx image.
THIS DESTROYS THE DISK CURRENTLY IN THE DRIVE.

Routes:
  .st   sector write, verified by gw reading each track back
  .scp  flux write, no verify possible (see --sectors note below)
  .stx  converted first - flux by default, which preserves the most and is the
        right choice for a protected game; pass --sectors for an unprotected
        disk to get a verified sector write instead

Options:
  --drive DRIVE  drive to write (default: $DEFAULT_DRIVE)
  --device DEV   serial port (default: gw auto-detects)
  --format FMT   format for sector writes (default: $DEFAULT_FORMAT)
  --tracks TSPEC restrict tracks, e.g. 'c=0-79:h=0-1'
  --sectors      .stx only: convert to .st and do a verified sector write
  --no-verify    skip gw's read-back verify (sector writes only)
  --keep         keep the converted intermediate next to the input image
  --yes          skip the confirmation prompt (for scripting)
  -h, --help     this help
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -h|--help)   usage; exit 0 ;;
            --drive)     require_value --drive "${2-}"; drive="$2"; shift 2 ;;
            --device)    require_value --device "${2-}"; device="$2"; shift 2 ;;
            --format)    require_value --format "${2-}"; format="$2"; format_set=1; shift 2 ;;
            --tracks)    require_value --tracks "${2-}"; tracks="$2"; shift 2 ;;
            --sectors)   sectors=1; shift ;;
            --no-verify) no_verify=1; shift ;;
            --keep)      keep=1; shift ;;
            --yes)       assume_yes=1; shift ;;
            -*)          die "unknown option '$1' (try --help)" ;;
            *)
                [ -z "$image" ] || die "unexpected extra argument '$1'"
                image="$1"; shift ;;
        esac
    done

    [ -n "$image" ] || { usage >&2; die "an image file is required"; }
    [ -f "$image" ] || die "no such file: $image"
}

choose_route() {
    local extension
    extension="$(lowercase_extension "$image")"
    case "$extension" in
        st)  route="$ROUTE_SECTOR" ;;
        scp) route="$ROUTE_FLUX" ;;
        stx) if [ "$sectors" -eq 1 ]; then route="$ROUTE_SECTOR"; else route="$ROUTE_FLUX"; fi ;;
        *)   die "unsupported image type '.$extension' - expected .st, .scp or .stx" ;;
    esac

    if [ "$sectors" -eq 1 ]; then
        case "$extension" in
            scp) die "--sectors applies to .stx input; a .scp holds flux, not sectors" ;;
            st)  die "--sectors is redundant: a .st is already a sector image" ;;
        esac
    fi
    # gw would take --format on a flux write, but that turns it into a decode-and-verify
    # operation rather than the raw flux reproduction the flux route exists to do.
    if [ -n "$format_set" ] && [ "$route" = "$ROUTE_FLUX" ]; then
        die "the flux route takes no --format (it writes raw flux); use --sectors for a format-driven write"
    fi
}

# .stx cannot be written directly, so it is converted to whichever form the chosen
# route needs. Conversions land in a temp dir unless --keep asks to keep them.
prepare_source() {
    if [ "$(lowercase_extension "$image")" != "stx" ]; then
        write_source="$image"
        return
    fi

    local module extension minimum_bytes output_dir base
    if [ "$route" = "$ROUTE_SECTOR" ]; then
        module="$HXCFE_ST_MODULE"; extension="st"; minimum_bytes="$MIN_CONVERTED_SECTOR_BYTES"
    else
        module="$HXCFE_SCP_MODULE"; extension="scp"; minimum_bytes="$MIN_CONVERTED_FLUX_BYTES"
    fi

    if [ "$keep" -eq 1 ]; then
        output_dir="$(dirname "$image")"
    else
        ensure_temp_dir
        output_dir="$temp_dir"
    fi
    base="$(basename "$image")"
    write_source="$output_dir/${base%.*}.$extension"

    # --keep writes beside the input, which in a dumps/<name>/ directory is exactly
    # where the .scp gold master lives. Never silently replace an existing file.
    [ ! -e "$write_source" ] \
        || die "refusing to overwrite $write_source - remove it or drop --keep"

    log "--- Converting STX -> ${extension} ---"
    hxcfe_convert "$image" "$write_source" "$module" 0

    # An STX gives hxcfe no per-track progress to report, so size is the only signal
    # that the conversion produced a real disk rather than a header's worth of noise.
    local produced
    produced="$(wc -c <"$write_source" | tr -d ' ')"
    [ "$produced" -ge "$minimum_bytes" ] \
        || die "converted image is implausibly small ($produced bytes, expected >= $minimum_bytes) - is $image truncated?"
    log "Converted -> $write_source ($produced bytes)"
}

# Writing is irreversible, so the last thing before it is an explicit confirmation.
confirm_overwrite() {
    if [ "$assume_yes" -eq 1 ]; then
        return
    fi
    # Read from the terminal, not stdin, so a piped invocation still prompts. Opening
    # it is the only reliable test: with no controlling terminal (cron, a detached
    # session) /dev/tty still passes -r but fails to open, so refuse on open failure
    # rather than hanging or writing unattended.
    # Braces keep bash's own redirection error out of the output; only our message shows.
    { exec 3</dev/tty; } 2>/dev/null \
        || die "no terminal available to confirm - re-run with --yes to write unattended"

    echo ""
    echo "  Image:  $image"
    echo "  Route:  $route write"
    echo "  Drive:  $drive"
    echo "  This ERASES the disk currently in drive $drive."
    printf 'Type %s to overwrite the disk in drive %s: ' "$CONFIRM_WORD" "$drive"

    local reply=""
    read -r reply <&3 || die "could not read confirmation - re-run with --yes"
    exec 3<&-
    [ "$reply" = "$CONFIRM_WORD" ] || die "aborted - nothing was written"
}

write_image() {
    local -a cmd=("$GW_BIN" write --pre-erase --drive "$drive")

    if [ -n "$device" ]; then
        cmd+=(--device "$device")
    fi
    if [ -n "$tracks" ]; then
        cmd+=(--tracks "$tracks")
    fi
    # gw only verifies tracks it built from a format (a MasterTrack carrying a verify
    # model). Raw flux has none, so on the flux route verify is unavailable rather
    # than disabled, and --no-verify would only change the wording gw prints.
    if [ "$route" = "$ROUTE_SECTOR" ]; then
        cmd+=(--format "$format")
        if [ "$no_verify" -eq 1 ]; then
            cmd+=(--no-verify)
        fi
    else
        log "Flux write: no sector verify - gw will report 'Verify unavailable'."
        log "Test the disk in the machine, or re-read it with backup_disk.sh and compare."
        if [ "$no_verify" -eq 1 ]; then
            log "(--no-verify is redundant on the flux route; not passed to gw.)"
        fi
    fi
    cmd+=("$write_source")

    log "--- Writing $route image to drive $drive ---"
    log "\$ ${cmd[*]}"

    # gw catches USB command errors (a write-protected disk being the everyday case),
    # prints "Command Failed: ..." and still exits 0, so the exit status alone would
    # report a successful write of nothing. The transcript is checked as well.
    ensure_temp_dir
    local transcript="$temp_dir/gw_write.log"
    if ! "${cmd[@]}" 2>&1 | tee "$transcript"; then
        die "gw write failed"
    fi
    ! grep -q "$GW_COMMAND_FAILED_MARKER" "$transcript" \
        || die "gw reported a command failure - the disk was NOT written (write-protected?)"
}

main() {
    parse_args "$@"
    choose_route

    # Only an .stx input needs hxcfe at all, and then only the two modules its route
    # actually uses; a plain .st or .scp write requires none.
    local -a required_modules=()
    if [ "$(lowercase_extension "$image")" = "stx" ]; then
        if [ "$route" = "$ROUTE_SECTOR" ]; then
            required_modules=("$HXCFE_STX_MODULE" "$HXCFE_ST_MODULE")
        else
            required_modules=("$HXCFE_STX_MODULE" "$HXCFE_SCP_MODULE")
        fi
    fi

    local device_info
    device_info="$(preflight ${required_modules[@]+"${required_modules[@]}"})"
    log_preflight "$device_info"

    # Converted before the prompt so a conversion failure cannot surface after the
    # user has already committed to erasing the disk.
    prepare_source
    confirm_overwrite
    write_image

    log ""
    log "Wrote $write_source to drive $drive ($route route)."
    if [ "$keep" -eq 1 ] && [ "$write_source" != "$image" ]; then
        log "Intermediate kept: $write_source"
    fi
}

main "$@"
