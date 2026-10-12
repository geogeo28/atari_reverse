"""THE ACCESSORIES' TURNS, PINNED (band 5 wave 3, the narrow door flip) — DATA, WRITTEN BY `tools/repin.py` FROM A RECORDED
RUN (`tools/pin_recorder.py`; recreate/README.md, "Re-pinning the rows that switch"), never by hand.

A row measured BEHIND OUR TRAP DOOR (`aes_ctlmgr.our_machine`: the accessory machines' rows) has, wherever an accessory
runs inside it, A TURN OF OURS that is not the screen manager's: the accessory's own text is the same bytes on both
shores, and every AES call it makes enters our door, marshal, opcode switch and routines where the ROM's run enters
the ROM's. Each is priced BY ITSELF (`bench/tier3.py`, `Turn`, `whose`: ruling W3-R3). `aes_switching.vet_its_turns`
holds, for every row it is asked about and on each blob, that the accessories' turns its run makes are THESE — `(our
build's own cycles, the ROM's AES subtree's in the same window of its run, our thunks' cycles)` each, in order — and
that a row with no line here makes none. The ROM's member is the ROM's run's: a record in which it moved is refused
by the tool, as for every other pin.

`{the row's registered name: {the blob's directory: (turn, ...)}}`.
"""
PINNED = {
    "aes_hctl_window, the up arrow held: sent, read by its owner, sent again; released": {
        "bench": ((5192, 7428, 0),),
        "bench_shipped": ((4886, 7428, 384),),
    },
    "aes_rom_ctlmgr, woken by a click on the closer, two more processes in a two-click wait: the count stepped from 3 by the button's arm": {
        "bench": ((42448, 56180, 0),),
        "bench_shipped": ((37596, 56180, 1892),),
    },
    "aes_rom_ctlmgr, woken by a click on the other window's title: WM_TOPPED written, its four stale words the ROM's stack's": {
        "bench": ((13428, 19324, 0),),
        "bench_shipped": ((12052, 19324, 700),),
    },
    "aes_rom_ctlmgr, woken by a click on the top window's closer: WM_CLOSED written to its owner, which reads it": {
        "bench": ((13584, 19996, 0),),
        "bench_shipped": ((12208, 19996, 700),),
    },
    "aes_rom_ctlmgr, woken by a click on the up arrow: the lock let go for a yield, WM_ARROWED written": {
        "bench": ((13584, 19996, 0),),
        "bench_shipped": ((12208, 19996, 700),),
    },
    "aes_rom_ctlmgr, woken by a press on the title, a drag and the release: WM_MOVED written": {
        "bench": ((13584, 19996, 0),),
        "bench_shipped": ((12208, 19996, 700),),
    },
    "aes_rom_ctlmgr, woken by the desk menu's accessory entry chosen: AC_OPEN written; the accessory hides the bar": {
        "bench": ((23282, 31196, 0), (8270, 11926, 0),),
        "bench_shipped": ((21172, 31196, 1984), (7200, 11926, 316),),
    },
}
