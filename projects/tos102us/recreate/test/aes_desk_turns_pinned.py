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
        "bench": ((231334, 299796, 0),),
        "bench_shipped": ((219462, 299796, 11740),),
    },
    "aes_ap_sendmsg, from the screen manager to the desk's full pipe: parked; freed by the desk's own read": {
        "bench": ((232024, 300600, 0),),
        "bench_shipped": ((220152, 300600, 11740),),
    },
    "aes_ct_msgup, AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise": {
        "bench": ((4570, 5808, 0),),
        "bench_shipped": ((4414, 5808, 276),),
    },
    "aes_ev_block, the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read": {
        "bench": ((231334, 299796, 0),),
        "bench_shipped": ((219462, 299796, 11740),),
    },
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); a title; the desk's turn again, in the next wait; the menu left, a click off it": {
        "bench": ((40392, 54134, 0), (39242, 52630, 0),),
        "bench_shipped": ((37396, 54134, 2140), (36242, 52630, 2140),),
    },
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); then a title, the menu left, a click off it": {
        "bench": ((40392, 54134, 0),),
        "bench_shipped": ((37396, 54134, 2140),),
    },
    "aes_rom_ctlmgr, woken by a button and the bar in one wake: the button's handler, then the menu worked": {
        "bench": ((254818, 337188, 0),),
        "bench_shipped": ((244724, 337188, 13368),),
    },
    "aes_rom_ctlmgr, woken by the bar, an item chosen: MN_SELECTED written to the desk, which reads it": {
        "bench": ((255160, 337980, 0),),
        "bench_shipped": ((245066, 337980, 13368),),
    },
}
