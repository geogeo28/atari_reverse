"""Demo player record for the `highscore` render — the single source of truth shared by the host
render (render_screen.py) and the on-target blob (HISCORE.BIN, built by gen_hiscore.py), so the
two agree byte-for-byte.

The high-score *table* is no longer fabricated: the verified g_init_scoretable writes the game's
own default table (scores 40000..10000, "..." names), then the verified g_update_highscore ranks
this player record into it. So the only demo datum is the 12-byte player score+name record.

Record layout: 6 score digits, \\0, a skip byte, a 3-char name, \\0 (draw_results_screen reads a
row as two strings, the second starting two bytes past the first's terminator). A leading '/'
(0x2f) is the game's blanked leading zero, so "/28000" renders as " 28000" and ranks like 28000.
"""
A_SCORE_BCD = 0x1824c              # 12-byte player score+name record (update_highscore's input)

PLAYER = (b"/28000\0\0YOU\0").ljust(12, b"\0")[:12]   # 28000 -> ranks 6th (between 30000 and 25000)
