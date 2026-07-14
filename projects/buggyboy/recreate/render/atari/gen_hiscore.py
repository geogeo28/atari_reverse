#!/usr/bin/env python3
"""Build HISCORE.BIN — the demo high-score data the `highscore` PRG loads at 0x1824c.

Single source of truth with the host render: it applies render/hiscore_demo.py's player record +
table onto the loaded (relocated) image and dumps the [BLOB_LO, BLOB_HI) range, so the on-target
bytes match what render_highscore_screen() pokes exactly — including the untouched gap between the
score record and the table (the score-line string draw_results_screen reads). The ranking/insert
into this table is then done on-target by the verified g_update_highscore.

Usage: gen_hiscore.py BUGGYBOY.PRG out/HISCORE.BIN
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "oracle"))    # recreate/oracle (loader)
sys.path.insert(0, str(HERE.parents[1] / "render"))    # recreate/render (hiscore_demo)
from loader import load_image                           # noqa: E402
import hiscore_demo as hs                               # noqa: E402


def main():
    prg, out = sys.argv[1], sys.argv[2]
    img = load_image(prg)
    img[hs.A_SCORE_BCD:hs.A_SCORE_BCD + len(hs.PLAYER)] = hs.PLAYER
    tbl = hs.table()
    img[hs.A_HIGHSCORE_TABLE:hs.A_HIGHSCORE_TABLE + len(tbl)] = tbl
    blob = bytes(img[hs.BLOB_LO:hs.BLOB_HI])
    Path(out).write_bytes(blob)
    print(f"{out}: {len(blob)} bytes  [{hs.BLOB_LO:#x},{hs.BLOB_HI:#x})")


if __name__ == "__main__":
    main()
