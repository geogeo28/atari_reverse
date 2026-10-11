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
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ap_tplay, the mouse played onto the menu bar and off it: the screen manager entered from a yield": {
        "bench": ((31140, 52100, 0),),
        "bench_shipped": ((27498, 52100, 1284),),
    },
    "aes_dispatch, opcode 11, as aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_dispatch, opcode 23, as aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_dispatch, opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_block, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_block, a wait for a key, the lock the desk's; the screen manager queues itself on the lock; then Return": {
        "bench": ((14702, 21870, 0),),
        "bench_shipped": ((13738, 21870, 652),),
    },
    "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager, which runs and waits; then Return": {
        "bench": ((115690, 155862, 1376),),
        "bench_shipped": ((103182, 155862, 7804),),
    },
    "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager; Return polled while it stands woken, before its turn": {
        "bench": ((111274, 148618, 1376),),
        "bench_shipped": ((98918, 148618, 7528),),
    },
    "aes_ev_block, a wait for a key; the screen manager, handed the lock, runs with it; then Return": {
        "bench": ((113068, 151888, 1376),),
        "bench_shipped": ((100556, 151888, 7804),),
    },
    "aes_ev_block, a wait for the lock the screen manager's menu holds, blocked; handed it when the menu lets go": {
        "bench": ((83516, 124096, 0),),
        "bench_shipped": ((72914, 124096, 4324),),
    },
    "aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_multi, blocked and woken — a key polled while the screen manager stands woken: a key and a message": {
        "bench": ((111274, 148618, 1376),),
        "bench_shipped": ((98918, 148618, 7528),),
    },
    "aes_ev_multi, blocked and woken — a key typed with the press wakes the desk before the writer writes: a key and a message": {
        "bench": ((167746, 240372, 1376),),
        "bench_shipped": ((150190, 240372, 10604),),
    },
    "aes_ev_multi, blocked and woken — a writer and a key in one wake: a key and a message": {
        "bench": ((198454, 279668, 1376),),
        "bench_shipped": ((175814, 279668, 12148),),
    },
    "aes_ev_multi, blocked and woken — a writer and the mouse into the rectangle: a rectangle and a message": {
        "bench": ((203222, 285068, 1376),),
        "bench_shipped": ((180484, 285068, 12332),),
    },
    "aes_ev_multi, blocked and woken — a writer and the press's ticks in one wake: a message and a timer": {
        "bench": ((196026, 276254, 1376),),
        "bench_shipped": ((173544, 276254, 11872),),
    },
    "aes_ev_multi, blocked and woken — a writer and the press's ticks in one wake: every event": {
        "bench": ((196026, 276254, 1376),),
        "bench_shipped": ((173544, 276254, 11872),),
    },
    "aes_ev_multi, blocked and woken — a writer and the press's ticks: eight bits held, a message and a timer": {
        "bench": ((196026, 276254, 1376),),
        "bench_shipped": ((173544, 276254, 11872),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: a key and a message": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: a message and a timer not run out": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_multi, blocked and woken — a writer wakes: every event, the timer not run out": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_multi, blocked and woken — a writer, a key and the press's ticks in one wake: a key, a message and a timer": {
        "bench": ((197844, 279942, 1376),),
        "bench_shipped": ((175366, 279942, 11872),),
    },
    "aes_ev_multi, blocked and woken — a writer, a key and the press's ticks in one wake: every event": {
        "bench": ((197844, 279942, 1376),),
        "bench_shipped": ((175366, 279942, 11872),),
    },
    "aes_ev_multi, blocked and woken — a writer, a key, the mouse, the press's ticks: every event": {
        "bench": ((203046, 287018, 1376),),
        "bench_shipped": ((180474, 287018, 12056),),
    },
    "aes_ev_multi, blocked and woken — a writer, the desk waiting for the bar's rectangle too": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_ev_multi, blocked and woken — a writer, then the mouse away: both rectangles and a message": {
        "bench": ((204746, 286746, 1376),),
        "bench_shipped": ((181958, 286746, 12424),),
    },
    "aes_fs_input, the screen manager's menu holding the screen": {
        "bench": ((83516, 124096, 0),),
        "bench_shipped": ((72914, 124096, 4324),),
    },
    "aes_marshal, marshalled: opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe": {
        "bench": ((198044, 278034, 1376),),
        "bench_shipped": ((175400, 278034, 12148),),
    },
    "aes_rom_ctlmgr, woken by a button and the bar in one wake: the button's handler, then the menu worked": {
        "bench": ((217224, 305434, 1376),),
        "bench_shipped": ((191090, 305434, 13360),),
    },
    "aes_rom_ctlmgr, woken by a click on the bar past the titles: the button's handler, nothing sent": {
        "bench": ((25514, 37510, 0),),
        "bench_shipped": ((22204, 37510, 1360),),
    },
    "aes_rom_ctlmgr, woken by a click on the closer, two more processes in a two-click wait: the count stepped from 3 by the button's arm": {
        "bench": ((91282, 158540, 0),),
        "bench_shipped": ((82480, 158540, 5336),),
    },
    "aes_rom_ctlmgr, woken by a click on the other window's title: WM_TOPPED written, its four stale words the ROM's stack's": {
        "bench": ((37450, 55798, 0),),
        "bench_shipped": ((32340, 55798, 1952),),
    },
    "aes_rom_ctlmgr, woken by a click on the top window's closer: WM_CLOSED written to its owner, which reads it": {
        "bench": ((89920, 155440, 0),),
        "bench_shipped": ((81114, 155440, 5336),),
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
        "bench": ((211886, 298022, 1376),),
        "bench_shipped": ((186698, 298022, 12848),),
    },
    "aes_rom_ctlmgr, woken by the desk menu's accessory entry chosen: AC_OPEN written; the accessory hides the bar": {
        "bench": ((194604, 281398, 688), (23082, 33128, 0),),
        "bench_shipped": ((171124, 281398, 11724), (20400, 33128, 1144),),
    },
    "aes_rom_ctlmgr, woken by the mouse onto a menu title, two more processes in a two-click wait: the count stepped from 3 by the bar's arm": {
        "bench": ((109490, 146012, 1376),),
        "bench_shipped": ((97008, 146012, 7288),),
    },
    "aes_rom_ctlmgr, woken by the mouse onto a menu title: the bar's handler drops the menu and waits in it": {
        "bench": ((109590, 146226, 1376),),
        "bench_shipped": ((97272, 146226, 7268),),
    },
}
