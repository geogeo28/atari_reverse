#!/usr/bin/env python3
"""Write HISCORE.BIN — the 12-byte demo player record the `highscore` PRG loads at score_bcd.

Single source of truth with the host render (render/hiscore_demo.py). The high-score *table* is
not shipped: the PRG builds it on-target with the verified g_init_scoretable, then g_update_highscore
ranks this player record into it.

Usage: gen_hiscore.py out/HISCORE.BIN
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "render"))    # recreate/render (hiscore_demo)
import hiscore_demo as hs                               # noqa: E402


def main():
    out = sys.argv[1]
    Path(out).write_bytes(hs.PLAYER)
    print(f"{out}: {len(hs.PLAYER)} bytes (player record -> score_bcd)")


if __name__ == "__main__":
    main()
