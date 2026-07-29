#!/usr/bin/env python3
"""run_crash_selftest.py — pin the on-target CRASH REPORTER: prove a 68000 fault is reported with a PC
that maps back to the right symbol.

The reporter (render/atari/crash.S + game_main.c's crash_report) exists for real hardware, where TOS
answers a fault with N bombs and nothing else — the vector number, never the code. It is therefore the
one piece of the shell that the bug it diagnoses is the only thing that normally runs it. This runner
closes that gap: it builds the GAME_CRASH_SELFTEST variant, whose main() deliberately does a `move.w`
on an ODD address (exception 3, the 3-bomb case), boots it headless with the TOS console echoed to
stdout (`--conout 2`), and checks the report that comes back:

  * a report was printed at all (the stubs took the vector instead of TOS's bomb handler);
  * VEC=03 — the vector reported is the one the fault raised;
  * FAULT is the odd address, and
  * TEXT+xxxxxxxx resolves, in build/game.elf, to `main` — the function that faulted.

That last check is the whole point of the tool: a PC that does not map back to a symbol reports nothing
useful. GEMDOS relocates the .PRG per machine, so the reporter prints the PC relative to p_tbase and this
runner resolves it against the UNRELOCATED build/game.elf, exactly as a human would.

Usage: python render/atari/run_crash_selftest.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402  Hatari + TOS ROM discovery

CRASH_PRG = "CRASHST.PRG"
ELF = run_hatari.BUILD / "game.elf"
EXPECTED_VECTOR = "03"                                     # address error: the 3-bomb case
EXPECTED_SYMBOL = "main"                                   # where GAME_CRASH_SELFTEST plants the fault
EXPECTED_STAGE = "01"                                      # CRASH_STAGE_BOOT, the milestone it plants after
EXPECTED_FRAME = "0000"                                    # no frame is presented that early in main()
RUN_VBLS = "12000"                                         # console echo slows the boot; this clears it
BOOT_TIMEOUT_S = 180
REPORT_BANNER = "*** BUGGYBOY CRASH ***"
TEXT_LABEL = "TEXT+"                                       # pinned to crash_report's own label literal


def build():
    # GAME_PRG makes this runner's CRASH_PRG constant authoritative (no stale build can pass for it) and
    # GAME_NO_STAGE keeps the variant in build/ — disk/ is the interactive-play drive.
    env = {**os.environ, "GAME_CRASH_REPORT": "1", "GAME_EXTRA_CFLAGS": "-DGAME_CRASH_SELFTEST",
           "GAME_PRG": CRASH_PRG, "GAME_NO_STAGE": "1"}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def boot_and_capture():
    """Boot the crash variant on a throwaway drive and return everything TOS echoed to the console.

    This does not use run_hatari.run(): that one waits for a SCREEN.BIN dump, and a crashed program never
    writes one — the report comes back over --conout instead. No data files are staged because the fault
    is planted at the top of main(), long before the asset load.
    """
    hatari, rom = run_hatari.tos_probe.find_hatari(), run_hatari.tos_probe.find_tos_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or TOS ROM not available (brew install hatari)")
    with tempfile.TemporaryDirectory() as d:
        drive = Path(d)
        (drive / CRASH_PRG).write_bytes((run_hatari.BUILD / CRASH_PRG).read_bytes())
        # Machine and memsize come from run_hatari's own defaults rather than literals, so this runner
        # follows RM_MEMSIZE with every other pin (the 1 MB memory-diet gate re-runs the suite at 1).
        args = [hatari, "--machine", "st", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--memsize", run_hatari.DEFAULT_MEMSIZE, "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", RUN_VBLS, "--conout", "2",
                "--harddrive", str(drive), "--auto", "C:\\" + CRASH_PRG]
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        return subprocess.run(args, env=env, capture_output=True, text=True,
                              timeout=BOOT_TIMEOUT_S).stdout


def parse_report(console):
    """The report's fields, as a dict. Returns None when no report was printed at all.

    Fields are `LABEL=value` except the PC offset, which the report prints as `TEXT+xxxxxxxx` because
    that is what it means to the human reading it off a TV. Both shapes are parsed; neither is defaulted,
    so a renamed label fails this runner loudly instead of resolving offset 0 to some arbitrary symbol.
    """
    if REPORT_BANNER not in console:
        return None
    body = console.split(REPORT_BANNER, 1)[1]
    fields = {}
    for token in body.split():
        if token.startswith(TEXT_LABEL):
            fields.setdefault("TEXT", token[len(TEXT_LABEL):])
        elif "=" in token:
            label, _, value = token.partition("=")
            fields.setdefault(label, value)
    return fields


def symbol_at(text_offset):
    """The build/game.elf function containing `text_offset` — the lookup a human does by hand.

    Returns None when the offset is past the last text symbol, rather than naming the final function for
    any arbitrarily large value: an offset outside TEXT must read as "unknown", never as a confident
    wrong answer.
    """
    nm = subprocess.run(["m68k-elf-nm", "-S", "-n", str(ELF)], capture_output=True, text=True,
                        check=True).stdout
    best, best_end = None, 0
    for line in nm.splitlines():
        parts = line.split()
        # `nm -S` prints "addr size type name" for sized symbols and "addr type name" for the rest.
        if len(parts) == 4 and parts[2].lower() == "t":
            addr, size = int(parts[0], 16), int(parts[1], 16)
            if addr <= text_offset < addr + size:
                return parts[3]
        elif len(parts) == 3 and parts[1].lower() == "t":
            addr = int(parts[0], 16)
            if addr <= text_offset and addr >= best_end:
                best, best_end = parts[2], addr
    return best


def main():
    build()
    report = parse_report(boot_and_capture())
    if report is None:
        print("FAIL: no crash report on the console — the stubs did not take the vector")
        sys.exit(1)

    missing = [f for f in ("VEC", "TEXT", "FAULT", "STAGE", "FRAME") if f not in report]
    if missing:
        print(f"FAIL: the report is missing {', '.join(missing)} — crash_report's labels and this "
              f"runner's parser have drifted apart")
        sys.exit(1)

    text_offset = int(report["TEXT"], 16)
    symbol = symbol_at(text_offset)
    fault = int(report["FAULT"], 16)
    problems = []
    if report["VEC"] != EXPECTED_VECTOR:
        problems.append(f"VEC={report['VEC']} (want {EXPECTED_VECTOR}, an address error)")
    if symbol != EXPECTED_SYMBOL:
        problems.append(f"TEXT+{text_offset:08X} resolves to {symbol} (want {EXPECTED_SYMBOL})")
    if not fault & 1:
        problems.append(f"FAULT={fault:08X} is even (an address error faults on an ODD address)")
    # The breadcrumbs: the fault is planted just past CRASH_STAGE_BOOT and before any frame is presented,
    # so these two values pin that CRASH_STAGE/CRASH_FRAME_TICK actually reach the report at all.
    if report["STAGE"] != EXPECTED_STAGE:
        problems.append(f"STAGE={report['STAGE']} (want {EXPECTED_STAGE}, CRASH_STAGE_BOOT) — the boot "
                        f"breadcrumb never reached the report")
    if report["FRAME"] != EXPECTED_FRAME:
        problems.append(f"FRAME={report['FRAME']} (want {EXPECTED_FRAME}: nothing is presented this early)")

    if problems:
        print("FAIL: " + "; ".join(problems))
        sys.exit(1)
    print(f"MATCH: fault reported as VEC={report['VEC']} at TEXT+{text_offset:08X} = {symbol}(), "
          f"odd address {fault:08X} — the crash reporter localises a fault on real hardware")
    sys.exit(0)


if __name__ == "__main__":
    main()
