"""THE SCREEN MANAGER'S TURNS, PINNED (FLIP 4: ctlmgr bound in C) — DATA, WRITTEN BY `tools/repin.py` FROM A RECORDED RUN
(`tools/pin_recorder.py`; recreate/README.md, "Re-pinning the rows that switch"), never by hand.

A row that switches on a machine whose screen manager is ours (`aes_takeover`) has our ctlmgr's turns inside it, each
priced BY ITSELF (`bench/tier3.py`, `Turn`). `aes_switching.vet_on_a_blob` holds, for every row it is asked about and on
each blob, that the turns its run makes are THESE — `(our build's own cycles, the ROM's AES subtree's in the same
window of its run (its cycles in the AES's text and Line-F handler), our thunks' cycles)` each, in order — and that a
row with no line here makes none. The ROM's member
is the ROM's run's: a record in which it moved is refused by the tool (the row's machine or its deliveries changed),
as for every other pin.

`{the row's registered name: {the blob's directory: (turn, ...)}}`.
"""
PINNED = {
    "aes_all_run, the screen manager's menu holds the lock: the caller waits until the menu is let go": {
        "bench": ((83516, 124096, 0),),
        "bench_shipped": ((72914, 124096, 4324),),
    },
    "aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ap_tplay, the mouse played onto the menu bar and off it: the screen manager entered from a yield": {
        "bench": ((31140, 52100, 0),),
        "bench_shipped": ((27498, 52100, 1284),),
    },
    "aes_ap_trecd, the mouse onto the menu bar and off it: the screen manager's turns inside the recording": {
        "bench": ((155830, 219072, 0),),
        "bench_shipped": ((138852, 219072, 8388),),
    },
    "aes_deskmain, the first entry, the DESKTOP.INF machine [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dgetdrv's own frame told]": {
        "bench": ((10310, 14662, 0), (20336, 29054, 0),),
        "bench_shipped": ((9498, 14662, 376), (17650, 29054, 1144),),
    },
    "aes_deskmain, the first entry, the DESKTOP.INF machine, as text [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dgetdrv's own frame told]": {
        "bench": ((10310, 14662, 0), (20336, 29054, 0),),
        "bench_shipped": ((9498, 14662, 376), (17650, 29054, 1144),),
    },
    "aes_deskmain, the first entry, the DESKTOP.INF machine, its cartridge's line a drive (LABELLED: F3 THE CARTRIDGE'S LINE A DRIVE) [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dgetdrv's own frame told]": {
        "bench": ((10310, 14662, 0), (20336, 29054, 0),),
        "bench_shipped": ((9498, 14662, 376), (17650, 29054, 1144),),
    },
    "aes_deskmain, the first entry, the desk alone (the blank disk) [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dgetdrv's own frame told]": {
        "bench": ((10310, 14662, 0), (20336, 29054, 0),),
        "bench_shipped": ((9498, 14662, 376), (17650, 29054, 1144),),
    },
    "aes_deskmain, the first entry, the files machine [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs; Dgetdrv's own frame told]": {
        "bench": ((10310, 14662, 0), (20336, 29054, 0),),
        "bench_shipped": ((9498, 14662, 376), (17650, 29054, 1144),),
    },
    "aes_dispatch, opcode 11, as aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_dispatch, opcode 23, as aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_dispatch, opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_block, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_block, a wait for a key, the lock the desk's; the screen manager queues itself on the lock; then Return": {
        "bench": ((14702, 21870, 0),),
        "bench_shipped": ((13738, 21870, 652),),
    },
    "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager, which runs and waits; then Return": {
        "bench": ((115390, 155862, 0),),
        "bench_shipped": ((102882, 155862, 6428),),
    },
    "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager; Return polled while it stands woken, before its turn": {
        "bench": ((110974, 148618, 0),),
        "bench_shipped": ((98618, 148618, 6152),),
    },
    "aes_ev_block, a wait for a key; the screen manager, handed the lock, runs with it; then Return": {
        "bench": ((112768, 151888, 0),),
        "bench_shipped": ((100256, 151888, 6428),),
    },
    "aes_ev_block, a wait for the lock the screen manager's menu holds, blocked; handed it when the menu lets go": {
        "bench": ((83516, 124096, 0),),
        "bench_shipped": ((72914, 124096, 4324),),
    },
    "aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_multi, blocked and woken — a key polled while the screen manager stands woken: a key and a message": {
        "bench": ((110974, 148618, 0),),
        "bench_shipped": ((98618, 148618, 6152),),
    },
    "aes_ev_multi, blocked and woken — a key typed with the press wakes the desk before the writer writes: a key and a message": {
        "bench": ((167446, 240372, 0),),
        "bench_shipped": ((149890, 240372, 9228),),
    },
    "aes_ev_multi, blocked and woken — a writer and a key in one wake: a key and a message": {
        "bench": ((198154, 279668, 0),),
        "bench_shipped": ((175514, 279668, 10772),),
    },
    "aes_ev_multi, blocked and woken — a writer and the mouse into the rectangle: a rectangle and a message": {
        "bench": ((202922, 285068, 0),),
        "bench_shipped": ((180184, 285068, 10956),),
    },
    "aes_ev_multi, blocked and woken — a writer and the press's ticks in one wake: a message and a timer": {
        "bench": ((195726, 276254, 0),),
        "bench_shipped": ((173244, 276254, 10496),),
    },
    "aes_ev_multi, blocked and woken — a writer and the press's ticks in one wake: every event": {
        "bench": ((195726, 276254, 0),),
        "bench_shipped": ((173244, 276254, 10496),),
    },
    "aes_ev_multi, blocked and woken — a writer and the press's ticks: eight bits held, a message and a timer": {
        "bench": ((195726, 276254, 0),),
        "bench_shipped": ((173244, 276254, 10496),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: a key and a message": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: a message and a timer not run out": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: every event, the timer not run out": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_multi, blocked and woken — a writer, a key and the press's ticks in one wake: a key, a message and a timer": {
        "bench": ((197544, 279942, 0),),
        "bench_shipped": ((175066, 279942, 10496),),
    },
    "aes_ev_multi, blocked and woken — a writer, a key and the press's ticks in one wake: every event": {
        "bench": ((197544, 279942, 0),),
        "bench_shipped": ((175066, 279942, 10496),),
    },
    "aes_ev_multi, blocked and woken — a writer, a key, the mouse, the press's ticks: every event": {
        "bench": ((202746, 287018, 0),),
        "bench_shipped": ((180174, 287018, 10680),),
    },
    "aes_ev_multi, blocked and woken — a writer, the desk waiting for the bar's rectangle too": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_ev_multi, blocked and woken — a writer, then the mouse away: both rectangles and a message": {
        "bench": ((204446, 286746, 0),),
        "bench_shipped": ((181658, 286746, 11048),),
    },
    "aes_fs_input, the screen manager's menu holding the screen": {
        "bench": ((83516, 124096, 0),),
        "bench_shipped": ((72914, 124096, 4324),),
    },
    "aes_marshal, marshalled: opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe": {
        "bench": ((197744, 278034, 0),),
        "bench_shipped": ((175100, 278034, 10772),),
    },
    "aes_rom_ctlmgr, woken by a button and the bar in one wake: the button's handler, then the menu worked": {
        "bench": ((216924, 305434, 0),),
        "bench_shipped": ((190790, 305434, 11984),),
    },
    "aes_rom_ctlmgr, woken by a click on the bar past the titles: the button's handler, nothing sent": {
        "bench": ((25514, 37510, 0),),
        "bench_shipped": ((22204, 37510, 1360),),
    },
    "aes_rom_ctlmgr, woken by a click on the closer, two more processes in a two-click wait: the count stepped from 3 by the button's arm": {
        "bench": ((91332, 158540, 0),),
        "bench_shipped": ((82532, 158540, 5336),),
    },
    "aes_rom_ctlmgr, woken by a click on the other window's title: WM_TOPPED written, its four stale words the ROM's stack's": {
        "bench": ((37450, 55798, 0),),
        "bench_shipped": ((32340, 55798, 1952),),
    },
    "aes_rom_ctlmgr, woken by a click on the top window's closer: WM_CLOSED written to its owner, which reads it": {
        "bench": ((89970, 155440, 0),),
        "bench_shipped": ((81166, 155440, 5336),),
    },
    "aes_rom_ctlmgr, woken by a click on the up arrow: the lock let go for a yield, WM_ARROWED written": {
        "bench": ((74502, 132434, 0),),
        "bench_shipped": ((66838, 132434, 4392),),
    },
    "aes_rom_ctlmgr, woken by a press on the title, a drag and the release: WM_MOVED written": {
        "bench": ((151002, 223514, 0),),
        "bench_shipped": ((133792, 223514, 11340),),
    },
    "aes_rom_ctlmgr, woken by the bar, an item chosen: MN_SELECTED written to the desk, which reads it": {
        "bench": ((211586, 298022, 0),),
        "bench_shipped": ((186398, 298022, 11472),),
    },
    "aes_rom_ctlmgr, woken by the desk menu's accessory entry chosen: AC_OPEN written; the accessory hides the bar": {
        "bench": ((194248, 281398, 0), (23082, 33128, 0),),
        "bench_shipped": ((170768, 281398, 11036), (20400, 33128, 1144),),
    },
    "aes_rom_ctlmgr, woken by the mouse onto a menu title, two more processes in a two-click wait: the count stepped from 3 by the bar's arm": {
        "bench": ((109190, 146012, 0),),
        "bench_shipped": ((96708, 146012, 5912),),
    },
    "aes_rom_ctlmgr, woken by the mouse onto a menu title: the bar's handler drops the menu and waits in it": {
        "bench": ((109290, 146226, 0),),
        "bench_shipped": ((96972, 146226, 5892),),
    },
}
