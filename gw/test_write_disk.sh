#!/usr/bin/env bash
#
# No-hardware smoke test for write_disk.sh. Pins route selection, the exact gw argv,
# the confirmation gate and the STX conversions. Never writes a disk: gw is stubbed
# for every invocation, and only hxcfe runs for real.

set -uo pipefail  # deliberately not -e: this script checks failing exit codes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT="$SCRIPT_DIR/write_disk.sh"
readonly LIB="$SCRIPT_DIR/gw_lib.sh"
readonly PYTHON_BIN="/usr/bin/python3"
readonly BLANK_ST_BYTES=737280   # 720K: 80 cyl * 2 heads * 9 sectors * 512, infers atarist.720
readonly ST_400_BYTES=409600     # atarist.400: single-sided 800 sectors
readonly ST_360_BYTES=368640     # atarist.360: single-sided 720 sectors
readonly UNKNOWN_ST_BYTES=100000 # matches no standard ST geometry

HXCFE_BIN="$(grep '^readonly HXCFE_BIN=' "$LIB" | cut -d'"' -f2)"
HXCFE_LIB_DIR="$(grep '^readonly HXCFE_LIB_DIR=' "$LIB" | cut -d'"' -f2)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
passed=0; failed=0

report() {
    if [ "$1" = ok ]; then printf 'PASS  %s\n' "$2"; passed=$((passed + 1))
    else printf 'FAIL  %s\n' "$2"; failed=$((failed + 1)); fi
}

# A zero-filled .st of an exact byte size (the write path infers geometry from size).
# bs=512 when the size is a whole number of sectors, else a slow byte-at-a-time fill.
make_sized_st() {  # make_sized_st <path> <bytes>
    local path="$1" bytes="$2"
    if [ $((bytes % 512)) -eq 0 ]; then
        dd if=/dev/zero of="$path" bs=512 count=$((bytes / 512)) 2>/dev/null
    else
        dd if=/dev/zero of="$path" bs=1 count="$bytes" 2>/dev/null
    fi
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

# Asserts the stubbed gw was invoked with exactly the expected argument string.
expect_argv() {  # expect_argv <description> <expected argv> <cmd...>
    local desc="$1" want="$2"; shift 2
    local got
    got="$("$@" 2>&1 | grep '^STUB-GW: write' | head -1)"
    [ "$got" = "STUB-GW: write $want" ] \
        && report ok "$desc" || report no "$desc"$'\n'"      want: STUB-GW: write $want"$'\n'"      got:  ${got:-<none>}"
}

build_stub_env() {
    mkdir -p "$WORK/stub"
    cat > "$WORK/stub/gw" <<'EOF'
#!/usr/bin/env bash
echo "STUB-GW: $*"
case "$1" in
  info)  echo "  Model:    Greaseweazle V4.1 (stub)" ;;
  # gw prints this and still exits 0 when the disk is write-protected.
  write) [ -n "${STUB_WRPROT:-}" ] && echo "Command Failed: Ack.Wrprot" ;;
esac
exit 0
EOF
    chmod +x "$WORK/stub/gw"
    # Only the library carries the tool paths, so the script itself is copied verbatim
    # and picks up the stub library from its own directory.
    sed -e "s|^readonly GW_BIN=.*|readonly GW_BIN=\"$WORK/stub/gw\"|" "$LIB" > "$WORK/stub/gw_lib.sh"
    cp "$SCRIPT" "$WORK/stub/write_stub.sh"
    chmod +x "$WORK/stub/write_stub.sh"
}

echo "=== argument handling ==="
expect_exit 0 "--help exits 0" "$SCRIPT" --help
expect_err "no such file"        "missing file is rejected"      "$SCRIPT" "$WORK/nope.st"
expect_err "image file is required" "no image argument is rejected" "$SCRIPT"
: > "$WORK/disk.img"
expect_err "unsupported image type" "unknown extension is rejected" "$SCRIPT" "$WORK/disk.img"

build_stub_env
STUB="$WORK/stub/write_stub.sh"
# The .st route now infers geometry from size, so fixtures must be real ST sizes.
make_sized_st "$WORK/disk.st" "$BLANK_ST_BYTES"     # 720K -> atarist.720
make_sized_st "$WORK/disk360.st" "$ST_360_BYTES"    # -> atarist.360
make_sized_st "$WORK/disk400.st" "$ST_400_BYTES"    # -> atarist.400
make_sized_st "$WORK/disk_unknown.st" "$UNKNOWN_ST_BYTES"
: > "$WORK/disk.scp"

echo "=== route selection and gw argv (stubbed) ==="
expect_argv ".st takes the verified sector route" \
    "--pre-erase --drive A --format atarist.720 $WORK/disk.st" \
    "$STUB" "$WORK/disk.st" --yes
expect_argv ".scp takes the flux route (no --format)" \
    "--pre-erase --drive A $WORK/disk.scp" \
    "$STUB" "$WORK/disk.scp" --yes
expect_argv "--no-verify passes through on the sector route" \
    "--pre-erase --drive A --format atarist.720 --no-verify $WORK/disk.st" \
    "$STUB" "$WORK/disk.st" --yes --no-verify
expect_argv "--no-verify is NOT passed on the flux route" \
    "--pre-erase --drive A $WORK/disk.scp" \
    "$STUB" "$WORK/disk.scp" --yes --no-verify
expect_argv "--tracks, --drive and --device pass through" \
    "--pre-erase --drive B --device /dev/cu.fake --tracks c=0-79:h=0-1 --format atarist.360 $WORK/disk360.st" \
    "$STUB" "$WORK/disk360.st" --yes --drive B --device /dev/cu.fake --tracks 'c=0-79:h=0-1' --format atarist.360
expect_err "a .scp holds flux"     "--sectors on a .scp is rejected"  "$STUB" "$WORK/disk.scp" --yes --sectors
expect_err "already a sector image" "--sectors on a .st is rejected"  "$STUB" "$WORK/disk.st" --yes --sectors
expect_err "flux route takes no --format" "--format on the flux route is rejected" \
    "$STUB" "$WORK/disk.scp" --yes --format atarist.720

echo "=== .st format inference (size -> format) ==="
expect_argv "a 409600-byte .st infers atarist.400" \
    "--pre-erase --drive A --format atarist.400 $WORK/disk400.st" \
    "$STUB" "$WORK/disk400.st" --yes
expect_argv "a 737280-byte .st infers atarist.720" \
    "--pre-erase --drive A --format atarist.720 $WORK/disk.st" \
    "$STUB" "$WORK/disk.st" --yes
expect_err "is 409600 bytes (atarist.400) but --format atarist.720 expects 737280" \
    "a .st whose size disagrees with --format is refused" \
    "$STUB" "$WORK/disk400.st" --yes --format atarist.720
expect_err "is 100000 bytes; known ST sizes" \
    "a .st of an unknown size is refused" \
    "$STUB" "$WORK/disk_unknown.st" --yes

echo "=== write-protected disk (gw exits 0 after 'Command Failed') ==="
wrprot_run() { STUB_WRPROT=1 "$STUB" "$WORK/disk.st" --yes; }
expect_err "disk was NOT written" "a write-protect failure is not reported as success" wrprot_run

echo "=== confirmation gate ==="
# No controlling terminal: /dev/tty passes -r but cannot be opened, so this must refuse.
no_tty_run() {
    "$PYTHON_BIN" -c "import os,subprocess,sys; os.setsid(); \
sys.exit(subprocess.run(['$STUB','$WORK/disk.st'],capture_output=True).returncode)"
}
expect_exit 1 "refuses when there is no terminal and no --yes" no_tty_run

# pty.fork gives the child a real controlling terminal we can type into.
pty_reply() {  # pty_reply <reply> <args...>
    "$PYTHON_BIN" - "$@" <<'PYEOF'
import os, pty, sys
reply, argv = sys.argv[1].encode() + b"\n", sys.argv[2:]
pid, fd = pty.fork()
if pid == 0:
    os.execv(argv[0], argv)
os.write(fd, reply)
out = b""
try:
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        out += chunk
except OSError:
    pass
_, status = os.waitpid(pid, 0)
sys.stdout.write(out.decode(errors="replace").replace("\r", ""))
sys.exit(os.waitstatus_to_exitcode(status))
PYEOF
}

# Asserted on exit status and the absence of a write rather than on the final message:
# macOS discards data still in the pty when the child exits, so the last line is racy.
abort_output="$(pty_reply n "$STUB" "$WORK/disk.st" 2>&1)"; abort_rc=$?
if [ "$abort_rc" -ne 0 ] \
   && grep -q 'Type y to overwrite' <<<"$abort_output" \
   && ! grep -q 'STUB-GW: write' <<<"$abort_output"; then
    report ok "answering 'n' aborts before gw write runs"
else
    report no "answering 'n' aborts before gw write runs (exit $abort_rc)"
fi
grep -q 'STUB-GW: write' <<<"$(pty_reply y "$STUB" "$WORK/disk.st" 2>&1)" \
    && report ok "answering 'y' proceeds to the write" || report no "answering 'y' proceeds to the write"

echo "=== real hxcfe STX conversions ==="
dd if=/dev/zero of="$WORK/blank.st" bs=1 count="$BLANK_ST_BYTES" 2>/dev/null
DYLD_LIBRARY_PATH="$HXCFE_LIB_DIR" "$HXCFE_BIN" \
    -finput:"$WORK/blank.st" -conv:ATARIST_STX -foutput:"$WORK/game.stx" >/dev/null 2>&1

# --keep puts the intermediate next to the input, which makes the path predictable
# enough to assert on; the default temp-dir path is random by nature.
expect_argv "default .stx route converts to SCP and writes flux" \
    "--pre-erase --drive A $WORK/game.scp" \
    "$STUB" "$WORK/game.stx" --yes --keep
[ -f "$WORK/game.scp" ] && report ok "--keep leaves the intermediate next to the input" \
                        || report no "--keep leaves the intermediate next to the input"
rm -f "$WORK/game.scp"

expect_argv "--sectors converts .stx to ST and writes sectors" \
    "--pre-erase --drive A --format atarist.720 $WORK/game.st" \
    "$STUB" "$WORK/game.stx" --yes --keep --sectors
rm -f "$WORK/game.st"

# Without --keep the conversion must land in a temp dir that the EXIT trap removes.
# The directory itself is checked, not just the absence of a file next to the input,
# so a broken trap cannot pass this.
default_run="$("$STUB" "$WORK/game.stx" --yes 2>&1)"
tmp_used="$(grep -o 'STUB-GW: write .*' <<<"$default_run" | awk '{print $NF}' | xargs dirname 2>/dev/null)"
if [ -n "$tmp_used" ] && [ "$tmp_used" != "$WORK" ] && [ ! -d "$tmp_used" ] && ! [ -f "$WORK/game.scp" ]; then
    report ok "default run cleans the temp dir up (trap)"
else
    report no "default run cleans the temp dir up (trap) - tmp_used='${tmp_used:-<none>}' still present?"
fi

echo "=== conversion safety ==="
# The dumps/<name>/ layout puts the gold master exactly where --keep wants to write.
mkdir -p "$WORK/dm"
cp "$WORK/game.stx" "$WORK/dm/dm.stx"
printf 'GOLD-MASTER-DO-NOT-CLOBBER' > "$WORK/dm/dm.scp"
gold_before="$(cksum <"$WORK/dm/dm.scp")"
expect_err "refusing to overwrite" "--keep will not clobber an existing gold master" \
    "$STUB" "$WORK/dm/dm.stx" --yes --keep
[ "$(cksum <"$WORK/dm/dm.scp")" = "$gold_before" ] \
    && report ok "the existing .scp is left untouched" || report no "the existing .scp is left untouched"

# A truncated STX still converts to a few hundred KB of SCP without hxcfe complaining.
printf 'RSY\0\3\0\1\0' > "$WORK/truncated.stx"
expect_err "implausibly small" "a truncated .stx is refused before writing" \
    "$STUB" "$WORK/truncated.stx" --yes

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
