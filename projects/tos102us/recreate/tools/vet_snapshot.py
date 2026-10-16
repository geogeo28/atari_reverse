#!/usr/bin/env python3
"""Refuse a fresh boot snapshot whose screen manager is not parked as the ROM's own boot leaves it.

    python tools/vet_snapshot.py build/boot_ram.bin     # exit 0: keep it; exit 1: capture again

WHY A CAPTURE NEEDS VETTING AT ALL: no two captures are bit-identical, and the cause is not the stop
point. HATARI'S FLOPPY IS NOT DETERMINISTIC: the same ROM, disk image and breakpoint, armed at
power-on (`--parse`), boot to register files that agree at every vertical blank up to the first
floppy wait and disagree from it on; with no disk in the drive two boots are bit-identical
(measured 2026-10-15, snapflake). So the start-up's interleaving with the interrupts differs from
boot to boot, and with it the RESIDUE that start-up leaves in dead slots inside the screen manager's
LIVE frames — the uninitialised QPB of its main wait's ev_multi (-8(a6), $a85a..$a861) and the
argument slot over its parked `rte` frame ($a828) were each seen to move. `aes_takeover.state_of`
compares those frames byte for byte, so a capture now and then (3 of 54 measured) stands where no
history of ours leaves it, and every row whose screen manager is ours is refused over it.

THE CHECK IS THE SUITE'S OWN PREMISE (`test_aes_takeover.py`'s first test): the snapshot's screen
manager stands exactly as `aes_boot.desk_machine()` — the ROM booted in the oracle from the pre-init
machine — leaves it. Under a second, so the capture rule runs it before a capture is kept.
"""
import argparse
import sys
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECREATE / "test"))


def screen_manager_as_booted(snapshot):
    """True when the screen manager over `snapshot` (bytes) stands as the ROM's boot leaves it."""
    import aes_takeover
    (booted, _machine), = aes_takeover.the_boot_s().items()
    try:
        return aes_takeover.state_of(snapshot) == booted
    except aes_takeover.Refused:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    if screen_manager_as_booted(args.snapshot.read_bytes()):
        return 0
    print(f"{args.snapshot}: the screen manager stands parked where the ROM's boot does not leave it — "
          f"a capture of another start-up history; capture again", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
