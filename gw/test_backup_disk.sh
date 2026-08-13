#!/usr/bin/env bash
#
# No-hardware smoke test for backup_disk.sh. Pins the argument handling, the
# --force cleanup and the SCP -> STX conversion leg. Never touches the drive:
# gw is stubbed everywhere a read would happen, and only hxcfe runs for real.

set -uo pipefail  # deliberately not -e: this script checks failing exit codes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT="$SCRIPT_DIR/backup_disk.sh"
readonly BLANK_ST_BYTES=737280   # 720K: 80 cyl * 2 heads * 9 sectors * 512
readonly SCP_HEADER_BYTES=688    # 16-byte header + 168 track offsets: no flux data

# Read the tool paths back out of the script so there is one source of truth.
HXCFE_BIN="$(grep '^readonly HXCFE_BIN=' "$SCRIPT" | cut -d'"' -f2)"
HXCFE_LIB_DIR="$(grep '^readonly HXCFE_LIB_DIR=' "$SCRIPT" | cut -d'"' -f2)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
passed=0; failed=0

report() {  # report <ok|no> <description>
    if [ "$1" = ok ]; then printf 'PASS  %s\n' "$2"; passed=$((passed + 1))
    else printf 'FAIL  %s\n' "$2"; failed=$((failed + 1)); fi
}

expect_exit() {  # expect_exit <code> <description> <cmd...>
    local want="$1" desc="$2"; shift 2
    "$@" >/dev/null 2>&1
    local got=$?
    [ "$got" -eq "$want" ] && report ok "$desc" || report no "$desc (exit $got, wanted $want)"
}

# A copy of the script wired to stub tools, so the read path can run with no drive.
build_stubbed_script() {
    mkdir -p "$WORK/stub"
    cat > "$WORK/stub/gw" <<'EOF'
#!/usr/bin/env bash
echo "STUB-GW: $*"
case "$1" in
  info) echo "  Model:    Greaseweazle V4.1 (stub)" ;;
  read) for a in "$@"; do out="$a"; done; printf 'FLUX' > "$out" ;;
  convert) for a in "$@"; do out="$a"; done; printf 'ST' > "$out"
           echo "Found 1440 sectors of 1440 (100%)" ;;
esac
EOF
    cat > "$WORK/stub/hxcfe" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "-modulelist" ]; then echo "ATARIST_STX;RW;Atari ST STX/Pasti Loader;*.stx;"; exit 0; fi
echo "Revolution 0 track generation... stub"
for a in "$@"; do case "$a" in -foutput:*) printf 'RSY\0STX' > "${a#-foutput:}" ;; esac; done
EOF
    chmod +x "$WORK/stub/gw" "$WORK/stub/hxcfe"
    sed -e "s|^readonly GW_BIN=.*|readonly GW_BIN=\"$WORK/stub/gw\"|" \
        -e "s|^readonly HXCFE_BIN=.*|readonly HXCFE_BIN=\"$WORK/stub/hxcfe\"|" \
        "$SCRIPT" > "$WORK/stub/backup_stub.sh"
    chmod +x "$WORK/stub/backup_stub.sh"
}

echo "=== argument handling ==="
expect_exit 0 "--help exits 0"                    "$SCRIPT" --help
expect_exit 1 "no disk name is rejected"          "$SCRIPT"
expect_exit 1 "unknown option is rejected"        "$SCRIPT" d --bogus
expect_exit 1 "disk name with '/' is rejected"    "$SCRIPT" foo/bar
expect_exit 1 "--revs swallowing a flag fails"    "$SCRIPT" d --revs --protected
expect_exit 1 "--revs with non-numeric fails"     "$SCRIPT" d --revs abc
expect_exit 1 "--convert-only missing file fails" "$SCRIPT" --convert-only "$WORK/nope.scp"

echo "=== stubbed read path (no drive) ==="
build_stubbed_script
STUB="$WORK/stub/backup_stub.sh"

"$STUB" precedence --rescue --revs 12 >/dev/null 2>&1
readlog="$WORK/stub/dumps/precedence/read.log"
if grep -q -- '--revs 12' "$readlog" && ! grep -q -- '--revs 8' "$readlog"; then
    report ok "explicit --revs beats --rescue"
else
    report no "explicit --revs beats --rescue (got: $(grep -o -- '--revs [0-9]*' "$readlog" | head -1))"
fi

"$STUB" rescuedefault --rescue >/dev/null 2>&1
grep -q -- '--revs 8' "$WORK/stub/dumps/rescuedefault/read.log" \
    && report ok "--rescue alone raises revolutions" || report no "--rescue alone raises revolutions"

# A stale .st from a previous run must not survive a --protected re-run.
"$STUB" staledisk >/dev/null 2>&1
"$STUB" staledisk --force --protected >/dev/null 2>&1
[ ! -e "$WORK/stub/dumps/staledisk/staledisk.st" ] \
    && report ok "--force clears stale artifacts" || report no "--force clears stale artifacts"

echo "=== real hxcfe conversion ==="
dd if=/dev/zero of="$WORK/blank.st" bs=1 count="$BLANK_ST_BYTES" 2>/dev/null
DYLD_LIBRARY_PATH="$HXCFE_LIB_DIR" "$HXCFE_BIN" \
    -finput:"$WORK/blank.st" -conv:SCP_FLUX_STREAM -foutput:"$WORK/synth.scp" >/dev/null 2>&1

if "$SCRIPT" --convert-only "$WORK/synth.scp" >/dev/null 2>&1 \
   && [ -s "$WORK/synth.stx" ] && [ "$(head -c 3 "$WORK/synth.stx")" = "RSY" ]; then
    report ok "--convert-only produces a valid STX"
else
    report no "--convert-only produces a valid STX"
fi

# hxcfe exits 0 on a flux-less SCP but converts nothing; that must not pass.
dd if="$WORK/synth.scp" of="$WORK/hdronly.scp" bs=1 count="$SCP_HEADER_BYTES" 2>/dev/null
expect_exit 1 "header-only SCP is rejected" "$SCRIPT" --convert-only "$WORK/hdronly.scp"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
