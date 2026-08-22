#!/usr/bin/env python3
"""M1 — the first execution of reconstructed Wonder Boy code on a 68000, asserted.

    bash atari/build.sh m1    && python3 atari/smoke.py m1
    bash atari/build.sh novbl && python3 atari/smoke.py novbl     # M1's negative control
    bash atari/build.sh m1    && python3 atari/smoke.py mono      # ...and its HARDWARE control

WHAT M1 CLAIMS is in README.md's milestone table and in wonderboy_main.c's header. In one sentence:
the reconstruction's own vertical-blank handler runs on a real machine at 50 Hz, and the two hardware
reads that steer the music tempo — the pair PORTABILITY.md §5 names as this project's false-green
surface — really answer for themselves.

THREE CONTROLS, because a check that cannot fail proves nothing, and one of them is not a code change
at all:

  novbl   one store suppressed (the level-4 vector install). Every assertion that depends on the
          machine driving the reconstruction must FAIL. The mode inverts its verdict, so a run that
          PASSES the comparison is the failure.
  mono    the SAME BINARY, booted with Hatari's monochrome monitor. `tempo_drop_value`'s first read
          is the MFP GPIP's monitor-detect bit, so the byte it leaves in the image must move from
          WB_SND_TICK_DROP_50HZ to WB_SND_TICK_DROP_MONO. A code control cannot show that the read is
          LIVE rather than a constant the compiler folded; changing the machine can.
  exit    every mode runs Hatari to the END of --run-vbls and asserts both halves of machine health:
          the emulator's exit status, and its log scanned for bus/address errors and halts whose PC
          is not TOS's own memory-sizing probe. THE STREAMS ARE MERGED, because Hatari writes all of
          its logging to stderr and a parser reading stdout scans an empty string for ever — that is
          a measured year-long blindness in the sibling project, and a run whose captured output does
          not contain Hatari's own banner RAISES here rather than being parsed.

Running past the program's own exit is not tidiness: WB.PRG installs two exception vectors and takes
supervisor, and an incomplete hand-back is only visible AFTER Pterm, when TOS is running on with
whatever the shim left hooked.
"""
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent
sys.path.insert(0, str(REC / "test"))
from layout import wb                                        # noqa: E402

DISK = HERE / "disk"
BUILD = HERE / "build"
OUT = HERE / "out"

# Hatari needs room for the 1 MiB image plus ~100 KB of program; 2 MB is the smallest that fits and
# 4 leaves the choice from mattering.
MEMSIZE_MB = 4
# TOS's OWN BOOT IS THOUSANDS OF VBLANKS, and this is the measurement rather than a guess: at 900
# the program was never Pexec'd at all — the desktop had not appeared yet — and the mode reported
# "no STATS.BIN" for a build that was fine. 6000 puts the boot, the run, the two IKBD resets
# (~300 ms each) and a long tail after Pterm inside one run, at ~3 s of wall clock under
# --fast-forward. The tail is not slack: an incomplete hand-back only shows up after the program has
# gone, which is why every mode here runs to the END rather than stopping at the dump.
RUN_VBLS = 6000
STATS_FILE = "STATS.BIN"

# ---- the record, named in the same order wonderboy_main.c declares it -------------------------
# THE SIZE IS CHECKED, so a field added in C and not here is a loud parse error rather than a
# silently misread record.
STATS_FORMAT = ">IIIIIIHHHHBBBBBB2x"
STATS_FIELDS = ("magic", "bytes", "image_base", "screen_base_published", "shim_vbl_ticks",
                "ikbd_bytes", "readback_failed", "readback_attempted", "vbl_counter",
                "floppy_idle_timer", "tick_drop_value", "psg_port_a_at_entry",
                "psg_port_a_after_run", "key_last_scancode", "sched_wait_returned",
                "ikbd_last_byte")
STATS_MAGIC = 0x57424131          # 'WBA1' — wonderboy_main.c's STATS_MAGIC


def readback_bits():
    """The RB_* bit numbers, READ OUT OF THE C rather than restated.

    Joust's lesson, taken at the start rather than after: a bit added in C and not classified here
    would never be asserted, and an unasserted check is indistinguishable from a passing one.
    """
    source = (HERE / "wonderboy_main.c").read_text()
    bits = {name: int(value)
            for name, value in re.findall(r"^#define\s+(RB_\w+)\s+(\d+)u", source, re.M)}
    if not bits:
        raise SystemExit("no RB_* bits found in wonderboy_main.c — the scraper has gone blind")
    return bits


RB = readback_bits()


def mask(*names):
    return sum(1 << RB[name] for name in names)


# Every bit, partitioned. A bit in neither list is a hard error below, which is what stops a
# sixteenth check being added in C and silently never asserted.
BOOT_BITS = ("RB_IMAGE_BASE_ALIGNED", "RB_VBL_VECTOR_INSTALLED", "RB_ACIA_VECTOR_INSTALLED",
             "RB_RESOLUTION_SET", "RB_SYNC_SET", "RB_SCREEN_BASE_PUBLISHED", "RB_VBL_TICKING",
             "RB_IKBD_REPLIED", "RB_PSG_PORT_A_DESELECTED")
TEARDOWN_BITS = ("RB_VBL_VECTOR_RESTORED", "RB_ACIA_VECTOR_RESTORED", "RB_RESOLUTION_RESTORED",
                 "RB_SYNC_RESTORED", "RB_SCREEN_BASE_RESTORED", "RB_PSG_PORT_A_RESTORED",
                 "RB_IKBD_DRAINED")

# ---- the image constants, from the C headers through test/layout.py ---------------------------
TICK_DROP_50HZ = wb("SND_TICK_DROP_50HZ")
TICK_DROP_MONO = wb("SND_TICK_DROP_MONO")
PSG_PORT_A_KEEP = wb("PSG_PORT_A_KEEP")
PSG_DRIVES_DESELECTED = wb("PSG_DRIVES_DESELECTED")

# gen_image.py's seeds, read from gen_image.py rather than restated — the same rule as RB above.
def gen_image_constant(name):
    source = (HERE / "gen_image.py").read_text()
    found = re.search(r"^%s = (0x[0-9a-fA-F]+|\d+)" % name, source, re.M)
    if not found:
        raise SystemExit(f"{name} is not a plain constant in gen_image.py")
    return int(found.group(1), 0)


def staged_screen_front():
    """WB_SCREEN_FRONT's longword, read out of the staged image the .PRG actually loaded.

    Not written down here and not taken from the .PRG's own report: it is the very value
    `publish_screen_base` handed the backend, so comparing against it turns check 5 from "the
    arithmetic produced something plausible" into "the arithmetic produced THIS". WB_STAGED_AT comes
    from project.toml for build.sh's reason — that file is where the 0x3f8 load base is argued for.
    """
    base = int(re.search(r"^load_base\s*=\s*(0x[0-9a-fA-F]+)",
                         (REC / "project.toml").read_text(), re.M).group(1), 16)
    at = wb("SCREEN_FRONT") - base
    blob = (DISK / "WB.IMG").read_bytes()
    if not 0 <= at and at + 4 <= len(blob):
        raise SystemExit(f"WB_SCREEN_FRONT is outside the staged block — cannot pin the addend")
    return int.from_bytes(blob[at:at + 4], "big")


FLOPPY_IDLE_TICKS = gen_image_constant("FLOPPY_IDLE_TICKS")
TICK_DROP_UNWRITTEN = gen_image_constant("TICK_DROP_UNWRITTEN")

# wonderboy_main.c's SMOKE_VBLS default, likewise.
SMOKE_VBLS = int(re.search(r"^#define SMOKE_VBLS (\d+)",
                           (HERE / "wonderboy_main.c").read_text(), re.M).group(1))


# ---- Hatari -----------------------------------------------------------------------------------

def find_tos():
    """$WB_TOS_ROM, then the workspace's own ROMs NEWEST FIRST, then Hatari's bundled EmuTOS.

    Newest first because the sibling project measured that **TOS 1.02 never runs the program at all**
    under a Hatari GEMDOS drive — a Hatari/TOS hard-disk limitation, not a property of the build —
    and `tools/hatari/` holds TOS102US.img beside TOS104US.img, so a plain sorted() picks the one
    that cannot work. Run this against more than one ROM anyway: two of the three bugs the sibling
    port found on target were found by adding a SECOND observation, and a second ROM was one of them.
    """
    named = os.environ.get("WB_TOS_ROM")
    if named:
        return named
    for candidate in sorted((HERE.parents[3] / "tools" / "hatari").glob("TOS*.img"), reverse=True):
        return str(candidate)
    return None      # Hatari falls back to its bundled EmuTOS


# TOS sizes memory by probing addresses that do not answer, and logs a bus error for each. The
# allowlist is the EXACT PC of that probe on each ROM, NOT "the PC is in ROM": a stale vector sends
# the CPU into ROM code, so a range test over ROM would excuse the very class this scan is for.
MEMORY_PROBE_PCS = ("$e00d98",      # EmuTOS
                    "$fc0174")      # TOS 1.04
FAULT_RE = re.compile(r"(Bus [Ee]rror|Address [Ee]rror|CPU halted|double bus)")
FAULT_PC_RE = re.compile(r"PC=(\$[0-9a-fA-F]+)")
HATARI_BANNER_RE = re.compile(r"Hatari v\d|WARN :|INFO :|Reading TOS")


def run_hatari(prg, monitor="rgb"):
    """Boot `prg` headless, run to the end of --run-vbls, and return the MERGED output."""
    for stale in (DISK / STATS_FILE,):
        stale.unlink(missing_ok=True)
    (DISK / "WB.PRG").write_bytes(Path(prg).read_bytes())

    rom = find_tos()
    args = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
            "--statusbar", "off", "--memsize", str(MEMSIZE_MB), "--monitor", monitor,
            "--run-vbls", str(RUN_VBLS), "--harddrive", str(DISK), "--auto", "C:\\WB.PRG"]
    if rom:
        args[1:1] = ["--tos", rom]
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / "hatari.log").write_text(done.stdout)
    return done.returncode, done.stdout, rom


def check_machine_health(status, log, assert_status=True):
    """Both halves: the emulator's return code, and its log scanned for what the code survives."""
    if not HATARI_BANNER_RE.search(log):
        raise SystemExit("FAIL: the captured output carries none of Hatari's own logging — the scan "
                         "below would be reading an empty string (see this file's header)")
    faults = []
    for line in log.splitlines():
        if not FAULT_RE.search(line):
            continue
        where = FAULT_PC_RE.search(line)
        if where and where.group(1) in MEMORY_PROBE_PCS:
            continue                      # TOS sizing memory: harmless, and PC-exact
        faults.append(line.strip())
    problems = []
    if faults:
        problems.append("unhealthy machine: " + " | ".join(faults[:4]))
    if assert_status and status != 0:
        problems.append(f"Hatari exited {status}")
    return problems


def read_stats():
    path = DISK / STATS_FILE
    if not path.exists():
        return None, "no STATS.BIN — the program never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(STATS_FORMAT)
    if len(blob) != want:
        return None, f"STATS.BIN is {len(blob)} bytes, expected {want}"
    record = dict(zip(STATS_FIELDS, struct.unpack(STATS_FORMAT, blob)))
    if record["magic"] != STATS_MAGIC:
        return None, f"STATS.BIN magic {record['magic']:#x} != {STATS_MAGIC:#x}"
    if record["bytes"] != want:
        return None, f"STATS.BIN says {record['bytes']} bytes, this parser expects {want}"
    return record, None


# ---- the assertions ----------------------------------------------------------------------------

def m1_checks(record):
    """The M1 claim, as a list of (name, ok, detail). Every one must hold for `m1`; the `novbl`
    control requires that AT LEAST the four machine-driven ones do not."""
    checks = []

    def add(name, ok, detail):
        checks.append((name, bool(ok), detail))

    unclassified = set(RB) - set(BOOT_BITS) - set(TEARDOWN_BITS)
    if unclassified:
        raise SystemExit(f"FAIL: RB bits added in C and never classified here: {sorted(unclassified)}")

    want_attempted = mask(*BOOT_BITS, *TEARDOWN_BITS)
    add("read-backs ran", record["readback_attempted"] == want_attempted,
        f"attempted {record['readback_attempted']:#06x}, expected exactly {want_attempted:#06x}")
    add("read-backs passed", record["readback_failed"] == 0,
        f"failed {record['readback_failed']:#06x}"
        + (" — " + ", ".join(n for n in RB if record["readback_failed"] >> RB[n] & 1)
           if record["readback_failed"] else ""))

    # 1. The reconstruction's own clock tracks the machine's. Both counters are 16-bit in the image
    #    and 32-bit in the shim, so compare the low word; they are equal, not merely close, because
    #    wb_vbl_tick increments its own counter and calls vbl_handler in the same breath.
    add("vbl_handler ran on the machine",
        record["vbl_counter"] == (record["shim_vbl_ticks"] & 0xffff) and record["vbl_counter"] >= SMOKE_VBLS,
        f"image WB_VBL_COUNTER={record['vbl_counter']}, shim ticks={record['shim_vbl_ticks']}, "
        f"asked for {SMOKE_VBLS}")

    # 2. The two REAL hardware reads steered. On a colour machine at 50 Hz the answer is
    #    WB_SND_TICK_DROP_50HZ; the `mono` control asserts the other arm.
    add("tempo_drop_value chose from real hardware",
        record["tick_drop_value"] == TICK_DROP_50HZ,
        f"WB_SND_TICK_DROP_VALUE={record['tick_drop_value']:#04x} "
        f"(50Hz={TICK_DROP_50HZ:#04x}, mono={TICK_DROP_MONO:#04x}, "
        f"never-written sentinel={TICK_DROP_UNWRITTEN:#04x})")

    # 3. The idle countdown expired and the real YM2149 took the write.
    add("floppy idle timer expired", record["floppy_idle_timer"] == 0,
        f"WB_FLOPPY_IDLE_TIMER={record['floppy_idle_timer']}, seeded to {FLOPPY_IDLE_TICKS}")
    add("the real YM2149 deselected the drives",
        record["psg_port_a_after_run"] & ~PSG_PORT_A_KEEP & 0xff == PSG_DRIVES_DESELECTED
        and record["psg_port_a_after_run"] & PSG_PORT_A_KEEP
            == record["psg_port_a_at_entry"] & PSG_PORT_A_KEEP,
        f"port A {record['psg_port_a_at_entry']:#04x} -> {record['psg_port_a_after_run']:#04x} "
        f"(keep mask {PSG_PORT_A_KEEP:#04x}, drives {PSG_DRIVES_DESELECTED})")

    # 4. sched_wait8's uncapped spin ended, on a byte the ACIA interrupt really wrote.
    add("sched_wait8 returned on a real interrupt's byte", record["sched_wait_returned"] == 1,
        f"sched_wait_returned={record['sched_wait_returned']}, "
        f"IKBD bytes filed={record['ikbd_bytes']}, last from the controller="
        f"{record['ikbd_last_byte']:#04x}, image scancode={record['key_last_scancode']:#04x}")

    # 5. The screen base was translated onto the machine, AND THE ADDEND IS PINNED. The first draft
    #    printed `published - image_base` and asserted only that it was positive and aligned, which
    #    a translation that had mangled the address entirely would still satisfy. It is now compared
    #    against WB_SCREEN_FRONT's own longword, read out of the staged image — the same bytes
    #    `publish_screen_base` handed the backend.
    #
    #    THIS IS WHAT KILLS THE BASE-BYTES-SWAPPED MUTANT AT M1, and only in one of its two homes.
    #    `wb_target_shifter_byte` decides which half of the shadow each register updates, and that
    #    code is SHARED with flip_screen; swapping it turns $078000 into $800700 and the compare
    #    fails (measured — see atari/README.md). What M1 still cannot reach is the swap in
    #    flip_screen's own two CALL SITES, because flip_screen does not run: that stays M2.
    want = staged_screen_front()
    got = record["screen_base_published"] - record["image_base"]
    add("the screen base is the translated one",
        got == want
        and record["screen_base_published"] % 256 == 0
        and record["image_base"] % 256 == 0,
        f"image at {record['image_base']:#x}, published {record['screen_base_published']:#x} "
        f"(= image + {got:#x}); WB_SCREEN_FRONT in the staged image is {want:#x}")
    return checks


# The subset of M1 that the `novbl` control must break. Everything here depends on the level-4
# vector reaching the reconstruction; nothing here can be true with that one store suppressed.
MACHINE_DRIVEN = ("read-backs passed", "vbl_handler ran on the machine",
                  "tempo_drop_value chose from real hardware", "floppy idle timer expired",
                  "the real YM2149 deselected the drives")

# ...EXCEPT ON A MACHINE WHOSE ENTRY STATE ALREADY SATISFIES ONE OF THEM.
#
# EmuTOS leaves YM2149 port A at 0x27 — the drives already deselected — so on that ROM the check
# passes without the reconstruction doing anything, and the control would report "did not break the
# check it exists to break" against a control that was working perfectly. That is a FALSE RED, and it
# is the same class as the vacuous-green above it: the assertion is exact, the machine offers no data
# that reaches the difference.
#
# So membership is decided from the RECORD rather than written down, and the exclusion is PRINTED —
# a check quietly dropped from a control is a check nobody is running.
ENTRY_STATE_VACUOUS = "the real YM2149 deselected the drives"


def machine_driven(record):
    """MACHINE_DRIVEN, minus any check this machine's entry state already satisfies."""
    vacuous = ((record["psg_port_a_at_entry"] & ~PSG_PORT_A_KEEP & 0xff) == PSG_DRIVES_DESELECTED)
    if not vacuous:
        return MACHINE_DRIVEN, None
    return (tuple(n for n in MACHINE_DRIVEN if n != ENTRY_STATE_VACUOUS),
            f"{ENTRY_STATE_VACUOUS!r} is excluded: port A already reads "
            f"{record['psg_port_a_at_entry']:#04x} at entry on this ROM, so the check is satisfied "
            f"by the entry state and cannot be broken by suppressing anything. Run the control on a "
            f"ROM that leaves the drives selected (TOS 1.04 gives 0x25) to exercise it.")


def report(title, checks):
    print(f"== {title}")
    for name, ok, detail in checks:
        print(f"   {'ok  ' if ok else 'FAIL'} {name}: {detail}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "m1"
    prg = {"m1": "WB-m1.PRG", "mono": "WB-m1.PRG", "novbl": "WB-novbl.PRG"}.get(mode)
    if prg is None:
        raise SystemExit(__doc__)
    prg = BUILD / prg
    if not prg.exists():
        raise SystemExit(f"{prg} — run `bash atari/build.sh {'m1' if mode == 'mono' else mode}` first")

    monitor = "mono" if mode == "mono" else "rgb"
    status, log, rom = run_hatari(prg, monitor)
    print(f"-- {mode}: TOS={rom or 'bundled EmuTOS'} monitor={monitor} "
          f"hatari exit={status} (full log in {OUT / 'hatari.log'})")

    problems = check_machine_health(status, log)
    record, why = read_stats()
    if record is None:
        problems.append(why)
        report(mode, [])
        raise SystemExit("FAIL: " + "; ".join(problems))

    checks = m1_checks(record)

    if mode == "novbl":
        # The control INVERTS its verdict: a run that passes the comparison is the failure.
        report("novbl (negative control — these MUST fail)", checks)
        must_break, excluded = machine_driven(record)
        if excluded:
            print(f"   note {excluded}")
        held = [name for name, ok, _ in checks if ok and name in must_break]
        if held:
            raise SystemExit("FAIL: the control did not break the checks it exists to break: "
                             + ", ".join(held))
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
        print("OK: every machine-driven M1 check fails with the vector install suppressed")
        return

    if mode == "mono":
        # The HARDWARE control. Only the tempo byte is asserted, and only that it MOVED — the rest
        # of M1 is the `m1` mode's business and a mono boot is not required to reproduce it.
        moved = record["tick_drop_value"] == TICK_DROP_MONO
        report("mono (hardware control)", [
            ("tempo_drop_value read the MONO monitor", moved,
             f"WB_SND_TICK_DROP_VALUE={record['tick_drop_value']:#04x}, expected "
             f"{TICK_DROP_MONO:#04x} (a colour boot gives {TICK_DROP_50HZ:#04x})")])
        if not moved or problems:
            raise SystemExit("FAIL: " + "; ".join(problems + ([] if moved else
                             ["the tempo byte did not move — the GPIP read is not live"])))
        print("OK: the same binary chooses a different tempo arm on a different machine")
        return

    report("m1", checks)
    problems += [f"{name}: {detail}" for name, ok, detail in checks if not ok]
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print("OK: M1 — the reconstruction ran on a 68000, driven by the machine")


if __name__ == "__main__":
    main()
