"""THE TURNS OF A PROCESS WHOSE TEXT IS THE ROM'S, OVER OUR AES, PINNED (band 6 slice B0, THE BINDING; ruling W6-R7) —
DATA, WRITTEN BY `tools/repin.py` FROM A RECORDED RUN (`tools/pin_recorder.py`; recreate/README.md, "Re-pinning the rows
that switch"), never by hand — BUT ONCE: band 6 W3a's stage 3 re-pinned by hand the ten triples of the five rows whose
desk's turn reads a message (ap_rdwr's, sendmsg's, ev_block's, ctlmgr's two; both blobs), because `repin.py` refuses a
moved ROM-side member and stage 3 moved exactly that one: the ROM's run is unchanged (each row's own total the same),
but the turn's ROM member is the ROM's AES-span cycles LESS our shore's there, and our shore no longer runs the ROM's
hndl_msg nor the handler copy — so it rose by exactly what the row's "OS both run" fell (+668/−668 for ap_rdwr,
sendmsg and ev_block, +2662/−2662 for both ctlmgr rows; the review RS3 verified each pair, and `vet_its_turns` holds
every triple exact).

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
        "bench": ((245632, 338492, 0),),
        "bench_shipped": ((233762, 338492, 11740),),
    },
    "aes_ap_sendmsg, from the screen manager to the desk's full pipe: parked; freed by the desk's own read": {
        "bench": ((246322, 339296, 0),),
        "bench_shipped": ((234452, 339296, 11740),),
    },
    "aes_ct_msgup, AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise": {
        "bench": ((4570, 5808, 0),),
        "bench_shipped": ((4414, 5808, 276),),
    },
    "aes_ev_block, the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read": {
        "bench": ((245632, 338492, 0),),
        "bench_shipped": ((233762, 338492, 11740),),
    },
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); a title; the desk's turn again, in the next wait; the menu left, a click off it": {
        "bench": ((41786, 55990, 0), (41004, 55008, 0),),
        "bench_shipped": ((38790, 55990, 2140), (38004, 55008, 2140),),
    },
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); then a title, the menu left, a click off it": {
        "bench": ((41786, 55990, 0),),
        "bench_shipped": ((38790, 55990, 2140),),
    },
    "aes_rom_ctlmgr, woken by a button and the bar in one wake: the button's handler, then the menu worked": {
        "bench": ((275058, 391066, 0),),
        "bench_shipped": ((264970, 391066, 13368),),
    },
    "aes_rom_ctlmgr, woken by the bar, an item chosen: MN_SELECTED written to the desk, which reads it": {
        "bench": ((275400, 391858, 0),),
        "bench_shipped": ((265312, 391858, 13368),),
    },
}

# ...AND THE ROM'S deskmain LOOP INSIDE THOSE TURNS (band 6 W3b's prep; the user's U1 (a), 2026-10-27: "the eight
# ROM-booted desk-turn rows are LABELLED 'the desk parked in the ROM's own deskmain frame', pinned by its cycles"). These
# rows run on machines THE ROM BOOTED: the desk is parked inside the ROM's deskmain frame, and its turn resumes there on
# both shores — so the ROM's deskmain loop runs in it on our shore too, flipped or not (no harness maps a ROM frame onto
# GCC's). Its cycles in each desk turn, in order, MEASURED (`bench/tier3.py`'s TALLY_OUR_DESKMAIN, held equal to the
# ROM's run in the same window) and the same on both blobs — the ROM's own text. `aes_switching.vet_its_turns` holds
# every row it vets to these, and a row not here to none: nothing runs that loop silently. Once deskmain is flipped the
# table says the label beside each such turn (`tier3._parked_of`). `{the row's registered name: (cycles, ...)}`.
# SEVEN ROWS: U1's "eight" are seven desk-turn rows and ct_msgup's, whose pinned turn is ANOTHER PROCESS'S (the
# accessory's, inside its wait for the rise), not the desk's [measured: the turn's owner, both blobs] — the label's
# class is the seven; ct_msgup is held to none (absent here).
PARKED_IN_THE_ROM_S_DESKMAIN = {
    "aes_ap_rdwr, the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read": (784,),
    "aes_ap_sendmsg, from the screen manager to the desk's full pipe: parked; freed by the desk's own read": (784,),
    "aes_ev_block, the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read": (784,),
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); a title; the desk's turn again, in the next wait; the menu left, a click off it": (726, 726),
    "aes_mn_do, on the bar past the titles; the desk's turn (Return); then a title, the menu left, a click off it": (726,),
    "aes_rom_ctlmgr, woken by a button and the bar in one wake: the button's handler, then the menu worked": (710,),
    "aes_rom_ctlmgr, woken by the bar, an item chosen: MN_SELECTED written to the desk, which reads it": (710,),
}
