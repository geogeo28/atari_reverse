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

# Read the tool paths back out of the shared library so there is one source of truth.
readonly LIB="$SCRIPT_DIR/gw_lib.sh"
HXCFE_BIN="$(grep '^readonly HXCFE_BIN=' "$LIB" | cut -d'"' -f2)"
HXCFE_LIB_DIR="$(grep '^readonly HXCFE_LIB_DIR=' "$LIB" | cut -d'"' -f2)"
GW_PYTHON="$(grep '^readonly GW_PYTHON=' "$LIB" | cut -d'"' -f2)"
readonly FIXTURE="$SCRIPT_DIR/dumps/wb_disk1/wb_disk1.scp"

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

# Asserts the SPECIFIC refusal, so a test cannot pass because something unrelated
# (a missing device, say) failed first.
expect_err() {  # expect_err <message pattern> <description> <cmd...>
    local pattern="$1" desc="$2"; shift 2
    local err rc
    err="$("$@" 2>&1 >/dev/null)"; rc=$?
    if [ "$rc" -ne 0 ] && grep -q "$pattern" <<<"$err"; then
        report ok "$desc"
    else
        report no "$desc (exit $rc, wanted message '$pattern')"$'\n'"      got: ${err:-<no stderr>}"
    fi
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
    # Stub greaseweazle Python: `py -c "import ..."` succeeds (library "present"), but any
    # script invocation (the injection worker) fails, so the stubbed backup deterministically
    # exercises its sector-only fallback without depending on a real greaseweazle install.
    cat > "$WORK/stub/py" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "-c" ] && exit 0
exit 1
EOF
    chmod +x "$WORK/stub/gw" "$WORK/stub/hxcfe" "$WORK/stub/py"
    # The tool paths live in the library now, so only the library needs rewriting; the
    # script is copied verbatim and picks up the stub library from its own directory.
    sed -e "s|^readonly GW_BIN=.*|readonly GW_BIN=\"$WORK/stub/gw\"|" \
        -e "s|^readonly HXCFE_BIN=.*|readonly HXCFE_BIN=\"$WORK/stub/hxcfe\"|" \
        -e "s|^readonly GW_PYTHON=.*|readonly GW_PYTHON=\"$WORK/stub/py\"|" \
        "$LIB" > "$WORK/stub/gw_lib.sh"
    cp "$SCRIPT" "$WORK/stub/backup_stub.sh"
    chmod +x "$WORK/stub/backup_stub.sh"
}

echo "=== argument handling ==="
expect_exit 0 "--help exits 0" "$SCRIPT" --help
expect_err "disk name is required"   "no disk name is rejected"          "$SCRIPT"
expect_err "unknown option"          "unknown option is rejected"        "$SCRIPT" d --bogus
expect_err "must not contain"        "disk name with '/' is rejected"    "$SCRIPT" foo/bar
expect_err "non-negative integer"    "--revs swallowing a flag fails"    "$SCRIPT" d --revs --protected
expect_err "non-negative integer"    "--revs with non-numeric fails"     "$SCRIPT" d --revs abc
expect_err "no such file"            "--convert-only missing file fails" "$SCRIPT" --convert-only "$WORK/nope.scp"

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
expect_err "converted no tracks" "header-only SCP is rejected" "$SCRIPT" --convert-only "$WORK/hdronly.scp"

# A regenerated STX must delete a stale Hatari .wd1772 sidecar bound to the OLD STX, or Hatari
# refuses to boot the new one ("Error restoring STX save buffer"). Removal happens before the
# injection branch, so this needs neither greaseweazle nor the fixture.
printf 'STALE' > "$WORK/synth.wd1772"
"$SCRIPT" --convert-only "$WORK/synth.scp" >/dev/null 2>&1
[ ! -e "$WORK/synth.wd1772" ] && [ -s "$WORK/synth.stx" ] \
    && report ok "regenerating an STX removes the stale .wd1772 sidecar" \
    || report no "stale .wd1772 sidecar survived STX regeneration"

echo "=== injection: protected fixture yields a bootable 0x61 STX ==="
# Needs the real flux fixture and greaseweazle; dumps/ is git-ignored, so SKIP on a fresh
# checkout rather than fail. --convert-only writes the .stx next to the .scp, so work on a copy.
cyl0_flag() {  # cyl0_flag <stx>
    "$GW_PYTHON" - "$1" <<'PY'
import struct, sys
d = open(sys.argv[1], "rb").read(); off = 16
for _ in range(d[10]):
    rs, fz, ns, fl, mf, tn, rt = struct.unpack_from("<IIHHHBB", d, off)
    if (tn & 0x7f, tn >> 7) == (0, 0): print(f"0x{fl:04x}"); break
    off += rs
PY
}
if [ -f "$FIXTURE" ] && "$GW_PYTHON" -c "import greaseweazle" 2>/dev/null; then
    cp "$FIXTURE" "$WORK/prot.scp"
    if "$SCRIPT" --convert-only "$WORK/prot.scp" >/dev/null 2>&1; then
        flag="$(cyl0_flag "$WORK/prot.stx")"
        [ "$flag" = "0x0061" ] \
            && report ok "backup STX carries track images (cyl 0 flag 0x0061)" \
            || report no "backup STX cyl 0 flag $flag, wanted 0x0061"
    else
        report no "backup --convert-only on protected fixture failed"
    fi
else
    printf 'SKIP  injection 0x61 test (fixture or greaseweazle absent)\n'
fi

echo "=== fallback: injection failure keeps the dump and warns sector-only ==="
# The stubbed Python fails every worker invocation, so injection cannot succeed. The backup
# must still finish (exit 0), warn that the STX is sector-only, and leave the .scp gold master
# and a valid (RSY) STX behind -- the flux is irreplaceable and must never be lost over this.
"$STUB" degraded >/dev/null 2>&1; degraded_rc=$?
ddir="$WORK/stub/dumps/degraded"
if [ "$degraded_rc" -eq 0 ] \
   && [ -s "$ddir/degraded.scp" ] \
   && [ "$(head -c 3 "$ddir/degraded.stx")" = "RSY" ] \
   && grep -q "sector-only" "$ddir/read.log"; then
    report ok "injection failure falls back to sector-only STX, backup survives"
else
    report no "injection-failure fallback (rc=$degraded_rc, scp/stx/warning missing)"
fi

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
