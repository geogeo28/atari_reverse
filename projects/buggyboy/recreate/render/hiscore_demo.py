"""Demo high-score data for the `highscore` render — the single source of truth shared by the
host render (render_screen.py) and the on-target blob (HISCORE.BIN, built by gen_hiscore.py), so
the two agree byte-for-byte. The table is invented demo data (the real game builds it over plays);
the ranking + insert of the player record is done by the *verified* g_update_highscore.

A row is "score\\0\\0NNN\\0" — 6 score digits then a 3-char name. draw_results_screen reads each
row as two strings and text_body skips two bytes past a terminator, which fixes names at 3 chars.
"""
A_SCORE_BCD = 0x1824c              # 12-byte player score+name record (update_highscore's input)
A_HIGHSCORE_TABLE = 0x18266        # per-leg table; leg 0 used for the demo
HS_ROW = 0xe                       # bytes per table row
HS_ROWS = 9

_NAMES = ("WRD", "SMT", "JON", "CLK", "KHN", "ROS", "NOV", "ABE", "FAL")
PLAYER = (b"625000\0\0YOU\0").ljust(12, b"\0")[:12]   # ranks into 5th place (between 650000/550000)

# HISCORE.BIN spans score_bcd through the end of the leg-0 table; the gap between them keeps its
# static value (draw_results_screen reads the score-line string there), so both sides must load the
# same bytes — gen_hiscore.py fills this range from the loaded image + these two pokes.
BLOB_LO = A_SCORE_BCD
BLOB_HI = A_HIGHSCORE_TABLE + HS_ROWS * HS_ROW        # 0x182e4


def _row(score, name):
    return (f"{score:06d}".encode() + b"\0\0" + name.encode() + b"\0").ljust(HS_ROW, b"\0")[:HS_ROW]


def table():
    return b"".join(_row((HS_ROWS - i) * 100000 + 50000, _NAMES[i]) for i in range(HS_ROWS))
