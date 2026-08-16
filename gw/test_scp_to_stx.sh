#!/usr/bin/env bash
#
# Functional test for scp_to_stx.sh: proves the tool turns a real protected-disk flux
# dump into a bootable, protection-preserving STX. The two pins that matter are (1) the
# protection tracks come out flagged 0x0061 (sector block + track image) and (2) Hatari
# boots the result with ZERO "no track image for read track" warnings -- the exact
# failure hxcfe's sector-only STX produces. Both need the wb_disk1.scp fixture and Hatari;
# the test skips (exit 0) when either is missing so the wider suite still runs elsewhere.

set -uo pipefail  # not -e: we assert on exit codes and grep results ourselves

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# gw_lib.sh gives us the hxcfe wrapper + module name so the test can rebuild the sector-only
# intermediate the injection differential compares against.
source "$SCRIPT_DIR/gw_lib.sh"
readonly SCRIPT="$SCRIPT_DIR/scp_to_stx.sh"
readonly VERIFY="$SCRIPT_DIR/verify_injection.py"
readonly FIXTURE="$SCRIPT_DIR/dumps/wb_disk1/wb_disk1.scp"
readonly TOS="$SCRIPT_DIR/../tools/hatari/TOS104US.img"
readonly PYTHON="/Users/geogeo/miniconda3/envs/atari_reverse/bin/python"

readonly PROTECTED_FLAG=0x0061         # sector block (0x01) + track image (0x60) as Aufit writes
readonly PROTECTED_CYLS="0 1 2 3 4"    # the Copylock 12-sector fuzzy band on Wonder Boy disk 1
readonly BOOT_VBLS=700                 # ~14s of emulated time: past the boot protection check
readonly NO_IMAGE_MSG="no track image for read track"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
passed=0; failed=0

report() {  # report <ok|no> <description>
    if [ "$1" = ok ]; then printf 'PASS  %s\n' "$2"; passed=$((passed + 1))
    else printf 'FAIL  %s\n' "$2"; failed=$((failed + 1)); fi
}

skip() { printf 'SKIP  %s\n' "$1"; exit 0; }

# Preconditions: without the fixture or Hatari there is nothing meaningful to assert.
[ -f "$FIXTURE" ]  || skip "fixture absent: $FIXTURE"
[ -f "$TOS" ]      || skip "TOS ROM absent: $TOS"
command -v hatari >/dev/null || skip "hatari not installed"
[ -x "$PYTHON" ] && "$PYTHON" -c "import greaseweazle" 2>/dev/null || skip "greaseweazle env absent"

out="$WORK/wb1.stx"
if bash "$SCRIPT" "$FIXTURE" "$out" >"$WORK/convert.log" 2>&1; then
    report ok "scp_to_stx.sh converts the fixture"
else
    report no "scp_to_stx.sh converts the fixture"; cat "$WORK/convert.log"
fi

# Read each protected track's flag word straight out of the STX record headers.
track_flag() {  # track_flag <stx> <cyl>
    "$PYTHON" - "$1" "$2" <<'PY'
import struct, sys
data = open(sys.argv[1], "rb").read(); want = int(sys.argv[2])
off = 16
for _ in range(data[10]):
    rec_size, _fz, _ns, flags, _mf, tnum, _rt = struct.unpack_from("<IIHHHBB", data, off)
    if (tnum & 0x7f, tnum >> 7) == (want, 0):
        print(f"0x{flags:04x}"); break
    off += rec_size
PY
}

# Injection differential: rebuild the sector-only intermediate hxcfe produces (deterministic,
# so it matches what scp_to_stx.sh ran internally) and pin the byte-surgery against it. The
# flag + boot checks below don't exercise the data_offset/rec_size fixups -- a mutant that
# dropped the offset shift would still flag 0x61 and still boot clean -- so this is the surface
# that catches a regression in exactly that arithmetic, and it needs no emulator.
if [ -f "$out" ]; then
    intermediate="$WORK/sector_only.stx"
    hxcfe -finput:"$FIXTURE" -conv:"$HXCFE_STX_MODULE" -foutput:"$intermediate" >/dev/null 2>&1
    if "$PYTHON" "$VERIFY" "$intermediate" "$out" >"$WORK/verify.log" 2>&1; then
        report ok "injection differential: offsets/sizes/sector data/fuzzy all correct vs hxcfe"
    else
        report no "injection differential vs hxcfe"; cat "$WORK/verify.log"
    fi
fi

# The 0x20 bit in PROTECTED_FLAG is cosmetic Aufit-fidelity, not a boot requirement: Hatari's
# reader only checks 0x40 (track image), so 0x41 would boot identically. We assert the full
# 0x61 to match the known-good Aufit output exactly.
if [ -f "$out" ]; then
    for cyl in $PROTECTED_CYLS; do
        got="$(track_flag "$out" "$cyl")"
        [ "$got" = "$PROTECTED_FLAG" ] \
            && report ok "cyl $cyl flagged $PROTECTED_FLAG (track image present)" \
            || report no "cyl $cyl flag $got, wanted $PROTECTED_FLAG"
    done
fi

# The real proof: boot headless and count the warning hxcfe's output triggers.
boot_warnings() {  # boot_warnings <stx> <log>
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy hatari \
        --tos "$TOS" --fast-boot on --fastfdc on --sound off --fast-forward on \
        --run-vbls "$BOOT_VBLS" --trace fdc --log-level warn --disk-a "$1" \
        >"$2" 2>&1 || true
    grep -c "$NO_IMAGE_MSG" "$2" || true
}

if [ -f "$out" ]; then
    warns="$(boot_warnings "$out" "$WORK/boot.log")"
    [ "$warns" -eq 0 ] \
        && report ok "Hatari boots with zero '$NO_IMAGE_MSG' warnings" \
        || report no "Hatari boot produced $warns '$NO_IMAGE_MSG' warning(s)"
fi

echo "----"
echo "passed=$passed failed=$failed"
[ "$failed" -eq 0 ]
