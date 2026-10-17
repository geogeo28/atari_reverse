"""THE TURNS OF A PROCESS WHOSE TEXT IS THE ROM'S, OVER OUR AES, PINNED (band 6 slice B0, THE BINDING; ruling W6-R7) —
DATA, WRITTEN BY `tools/repin.py` FROM A RECORDED RUN (`tools/pin_recorder.py`; recreate/README.md, "Re-pinning the rows
that switch"), never by hand.

Since the Line-F table is ours at every Tier 3 run's entry, THE DESK'S TURN inside a row (`aes_switching.THE_DESK_S`)
— and another process's resumed in the ROM's AES text on a machine with no door (`ANOTHER_PROCESS_S`) — runs the ROM's
own text over OUR AES: every Line-F call it makes enters our table. Each is A TURN OF OURS, priced by itself as an
accessory's is (`bench/tier3.py`, `Turn`, `whose`): our build's own cycles in the window against the ROM's AES-span
cycles in the same window of its run LESS what our shore spent in those spans (the process's own text, the ROM's
leaves it calls, the handler copy its Line-F calls run). `aes_switching.vet_its_turns` holds, for every row it is
asked about and on each blob, that those turns its run makes are THESE — `(ours, the ROM's, our thunks')` each, in
order — and that a row with no line here makes none.

`{the row's registered name: {the blob's directory: (turn, ...)}}`.
"""
PINNED = {
    "aes_ap_rdwr, the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read": {
        "bench": ((243092, 324602, 0),),
        "bench_shipped": ((231220, 324602, 11740),),
    },
    "aes_ap_sendmsg, from the screen manager to the desk's full pipe: parked; freed by the desk's own read": {
        "bench": ((243782, 325406, 0),),
        "bench_shipped": ((231910, 325406, 11740),),
    },
    "aes_ct_msgup, AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise": {
        "bench": ((4570, 5808, 0),),
        "bench_shipped": ((4414, 5808, 276),),
    },
    "aes_ev_block, the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read": {
        "bench": ((243092, 324602, 0),),
        "bench_shipped": ((231220, 324602, 11740),),
    },
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); a title; the desk's turn again, in the next wait; the menu left, a click off it": {
        "bench": ((40744, 55126, 0), (39594, 53622, 0),),
        "bench_shipped": ((37748, 55126, 2140), (36594, 53622, 2140),),
    },
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); then a title, the menu left, a click off it": {
        "bench": ((40744, 55126, 0),),
        "bench_shipped": ((37748, 55126, 2140),),
    },
    "aes_rom_ctlmgr, woken by a button and the bar in one wake: the button's handler, then the menu worked": {
        "bench": ((267478, 366028, 0),),
        "bench_shipped": ((257384, 366028, 13368),),
    },
    "aes_rom_ctlmgr, woken by the bar, an item chosen: MN_SELECTED written to the desk, which reads it": {
        "bench": ((267820, 366820, 0),),
        "bench_shipped": ((257726, 366820, 13368),),
    },
}
