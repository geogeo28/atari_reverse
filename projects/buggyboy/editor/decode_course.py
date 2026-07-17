"""decode_course.py — dump a leg of COURSES.DAT in human-readable form.

Usage:
    python decode_course.py [PATH/TO/COURSES.DAT] [--leg N] [--records K] [--raw]

Grounds the editor: run it to see the real record stream, scroll table and
dashboard block for a leg before touching the editing side.
"""
from __future__ import annotations

import sys
from pathlib import Path

import course_format as cf

DEFAULT_DAT = Path(__file__).resolve().parents[1] / "bin" / "COURSES.DAT"


def dump_leg(data: bytes, leg: int, nrecords: int, raw: bool) -> None:
    anchor = cf.leg_stream_anchor(leg)
    print(f"=== LEG {leg} ===")
    print(f"file size            0x{len(data):x} ({len(data)} bytes)")
    print(f"dashboard bitmap     file 0x{leg * cf.DASH_LEG_STRIDE:x} "
          f"({cf.DASH_ROWS} rows x 0x{cf.DASH_SRC_STRIDE:x} bytes)")

    # scroll table: 16 bytes at buf_a + leg*0x10
    st_off = cf.buf_a(leg * cf.SCROLL_TABLE_STRIDE)
    scroll = data[st_off:st_off + cf.SCROLL_TABLE_STRIDE]
    print(f"scroll table         file 0x{st_off:x}: "
          f"{' '.join(f'{b:02x}' for b in scroll)}")

    # object/palette selector byte
    sel_off = cf.buf_a(cf.OBJDISP_SEL_OFF + (leg << 5))
    print(f"obj/pal selector     file 0x{sel_off:x}: 0x{data[sel_off]:02x}")

    print(f"course anchor        file 0x{anchor:x} (records read backward)")
    print()
    print(f"{'#':>3} {'file':>7} {'mask':>6} {'ctl':>4} {'rows':>4} {'dec':>4} "
          f"{'marker':>6} {'class':<12} payload")
    print("-" * 74)

    records = cf.decode_leg(data, leg, max_records=nrecords)
    for r in records:
        pl = r.payload.hex(" ") if r.payload else ""
        if raw:
            pl += f"   [{data[r.file_off:r.file_off + 8].hex(' ')}]"
        print(f"{r.index:>3} 0x{r.file_off:05x} 0x{r.select_mask:04x} "
              f"0x{r.control:02x} {r.row_count:>4} {r.decay_seed:>+4} "
              f"0x{r.marker:04x} {r.classify_marker():<12} {pl}")

    # quick histogram of marker classes
    from collections import Counter
    hist = Counter(r.classify_marker() for r in records)
    print()
    print("marker classes:", dict(hist))


def main(argv: list[str]) -> int:
    path = DEFAULT_DAT
    leg, nrecords, raw = 0, 64, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--leg":
            leg = int(argv[i + 1]); i += 2
        elif a == "--records":
            nrecords = int(argv[i + 1]); i += 2
        elif a == "--raw":
            raw = True; i += 1
        else:
            path = Path(a); i += 1
    data = path.read_bytes()
    dump_leg(data, leg, nrecords, raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
