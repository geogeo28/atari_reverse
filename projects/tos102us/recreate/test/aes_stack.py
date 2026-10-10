"""A PROCESS'S STACK — what our build's own code can take of the stack a process of the AES runs on, and what it is
measured to take (`test_aes_stack.py`; ruling W2-R3 of AES band 5 wave 2).

THE SCREEN MANAGER (PD1) runs ctlmgr and everything under it on the stack of its own UDA: `[uda + 74, the top)`,
1,196 bytes on this machine (`aes_gemctrl.its_stack`: read off the machine). Under the ROM's ctlmgr the frames
there are Alcyon's; under ours they are GCC's, about half as deep again — and below the span lies PD1's own saved
context, which savestate rewrites at every park: an overflow would be silent and intermittent. FOUR TERMS, each
of THE BUILD THAT SHIPS, none borrowed from the ROM where ours differs:

  * OUR OWN FRAMES, READ OFF THE BUILD (`aes_switch.StackReading`, `bound`): the deepest any path of a blob's
    listing takes the stack from the screen manager's entry — `aes_rom_ctlmgr`, FOUND BY SYMBOL (until a blob links
    it: the four handlers under a declared allowance) — and the deepest it takes a `trap #2` at. What the reading
    is TOLD, each declaration held to the build or the machine by a test: dsptch LEAVES the stack; ob_user calls
    AN APPLICATION'S ROUTINE; everyobj calls THE ROUTINE ITS CALLER HANDS IT; `$a000` in gsx_mfsave is a Line-A
    trap of a measured need; forker's and mchange's pointers, as the dispatcher's reading declares them.
  * THE OS UNDER A `trap #2`, BY THE VDI CALL (`os_needs`): MEASURED — a pattern laid under the trap's frame, read
    where the trap returns — with OUR OWN VDI linked under the trap for our shore (`aes_switch`'s staging of the
    build's VDI, band 4's: our C goes 32 bytes deeper than the ROM's), the ROM's for the ROM's.
  * THE INTERRUPTS' NEST (`nest`): a horizontal blank's 8 bytes, a vertical blank inside it, an MFP interrupt
    inside that — each handler's need MEASURED on the build's own entries.
  * WHAT AN APPLICATION'S ROUTINE IS LEFT (`at_the_userdef_call`): a G_USERDEF's draw routine runs on THIS stack
    under our frames, and no reader bounds it — so what the verdict says of it is the bytes it has, and how many
    fewer than under the ROM.

BESIDE THE BOUND, THE MEASURED RUNS FROM THE REAL ENTRY (`measured`): a machine whose screen manager is OURS
(`aes_boot`'s takeover) and the ROM-booted one beside it, each continued from its idle by what a hand does — a
gadget dragged, a menu dropped — and the lowest byte of PD1's stack each stores. TWO LIMITS, said where the numbers
are (`report`): a run's depth is its lowest STORE, not its lowest SP (`untouched_at_most` bounds the difference
from the listing), and no interrupt is taken at a run's deepest point — the nest is added by arithmetic.

WHAT IS NOT READ HERE (wave 3, ruling W2-R5): a process that enters the AES by `trap #2` runs the opcode switch,
whose jump table the reading refuses by name — no path read here goes through it (held by a test).
"""
import functools
import struct
from collections import namedtuple

import derived
from harness import addrs, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_boot
import aes_event
import aes_gemctrl
import aes_gsx
import aes_switch
import aes_switching
import case
import isr
import transcription

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = aes_event.OS_BUS_ADDR_MASK
SCREEN_MANAGER = aes.SCREEN_MANAGER_PD
BLOBS = aes_switch.BLOBS
# A SHORE: whose code a run is of — the ROM's own, or one of the two blobs', BY ITS NAME (a key of BLOBS).
THE_ROM_S = "the ROM's own"


def blob_of(shore):
    return rom_bench.RomBench(BLOBS[shore])


def shore_of(blob):
    return next(shore for shore in BLOBS if blob_of(shore).elf == blob.elf)

# ---- THE BOUND: what the reading is told, and from where it reads ----------------------------------------------------------
SCREEN_MANAGER_ENTRY = "aes_rom_ctlmgr"         # what our ictlmgr hands pstart: entered by switchto's `rte`
PSTART = "aes_pstart"
HANDLERS = ("aes_hctl_button", "aes_hctl_rect", "aes_hctl_window", "aes_ct_msgup")
# UNTIL A BLOB LINKS THE ENTRY: what ctlmgr itself holds above a handler's first instruction — its frame (24 bytes,
# the ROM's own: six answer words, three saved registers), a handler's arguments as the C ABI passes them (the image
# and two longword slots) and the return address. AN ALLOWANCE, declared: the reading replaces it the moment the
# symbol exists (`entered_at`), and a test reddens if it then does not.
CTLMGR_S_OWN_BYTES_ALLOWED = 24 + 3 * LONG_BYTES + LONG_BYTES
LEAVES_THE_STACK = ("aes_dsptch",)
CALLS_WHAT_IT_IS_HANDED = ("aes_everyobj",)
AN_APPLICATION_S_ROUTINE = aes_switch.AN_APPLICATION_S_ROUTINE
# THE POINTERS OF THE MACHINE on the screen manager's paths, and what each can hold: the dispatcher's own two
# (`aes_switch.THROUGH_A_POINTER`: ev_multi runs forker too) and ob_user's — a USERBLK's code, an application's.
THROUGH_A_POINTER = {**aes_switch.THROUGH_A_POINTER, "aes_ob_user": (AN_APPLICATION_S_ROUTINE,)}
THE_LINE_A_INIT = ".short 0xa000"               # gsx_mfsave's `$a000`: the one Line-A trap on the screen manager's paths
THE_OPCODE_SWITCH = "aes_dispatch"              # `src/aes/gemsuper.c`: compiled as a jump table, read in wave 3
ALLOWED = "ctlmgr's own bytes (allowed: no blob links it)"
EXCEPTION_FRAME_BYTES = aes_switch.EXCEPTION_FRAME_BYTES

Bound = namedtuple("Bound", "entered_at allowed deepest chain at_a_trap trap_chain")
Bound.__doc__ = """`entered_at`: the functions the reading starts at; `allowed`: the bytes added above them (0 once the
entry links); `deepest`, `chain`: the deepest SP our own code reaches, in bytes below the stack's top, and the calls
that lead there, `(function, the bytes it holds)` each; `at_a_trap`, `trap_chain`: the same for the deepest SP a
`trap #2` is taken at."""


@functools.cache
def reading(elf):
    """THE READING of the blob at `elf` as a process's paths are read: one, every function read once."""
    return aes_switch.StackReading(elf, THROUGH_A_POINTER, leaves_the_stack=LEAVES_THE_STACK,
                                   calls_what_it_is_handed=CALLS_WHAT_IT_IS_HANDED,
                                   takes_an_exception={THE_LINE_A_INIT: line_a_need()})


def links(elf, symbol):
    return any(each.name == symbol for each in transcription.symbol_table(elf))


def entered_at(elf):
    """`(the functions the screen manager's reading starts at, the bytes allowed above them)`: the entry BY SYMBOL
    where the blob links one — entered by an `rte`, nothing above it — or the four handlers under the allowance."""
    if links(elf, SCREEN_MANAGER_ENTRY):
        return (SCREEN_MANAGER_ENTRY,), 0
    return HANDLERS, CTLMGR_S_OWN_BYTES_ALLOWED


def bound(blob):
    """The screen manager's `Bound` on `blob`."""
    read, (entries, allowed) = reading(blob.elf), entered_at(blob.elf)
    above = [(ALLOWED, allowed)] if allowed else []
    deepest = max(entries, key=lambda entry: read.of(entry).deepest)
    trapped = max(entries, key=lambda entry: aes_switch.depth_of((read.of(entry).at_a_trap,)))
    return Bound(entries, allowed, allowed + read.of(deepest).deepest, above + read.chain(deepest),
                 allowed + read.of(trapped).at_a_trap, above + read.chain(trapped, to_the_trap=True))


def at_the_userdef_call(blob):
    """`(the bytes below the stack's top at which AN APPLICATION'S ROUTINE is entered at its deepest — ob_user's
    `jsr (a0)`, the return address pushed — the calls that lead there)`: what stands ABOVE code no reader bounds."""
    read, (entries, allowed) = reading(blob.elf), entered_at(blob.elf)
    reached = [(entry, read.deepest_to(entry, AN_APPLICATION_S_ROUTINE)) for entry in entries]
    entry, (depth, path) = max(((entry, to) for entry, to in reached if to), key=lambda each: each[1][0])
    return allowed + depth, (entry, *path)


def _calls(text, callee):
    target = aes_switch.NAMED_TARGET.search(text)
    return bool(target) and target.group(2) == callee and not target.group(3) and text.startswith(("jsr", "bsr"))


def process_entries(elf):
    """EVERY PROCESS ENTRY OF THE BUILD: the functions a caller of pstart names BY VALUE — what it hands as a new
    process's code. (An application's entry is no code of the build: gotopgm's `rte` leaves for it.)"""
    read = reading(elf)
    return {read.named_by_value(text) for body in read.functions().values() if any(_calls(text, PSTART) for _at, text in body)
            for _at, text in body} - {None}


def routines_handed_to(elf, callee):
    """Every routine a call of `callee` hands it, over the whole blob: `{(caller, the routine)}`."""
    read = reading(elf)
    return {(caller, read.handed_at(caller, at)) for caller, body in read.functions().items()
            for at, text in body if _calls(text, callee)}


def untouched_at_most(blob):
    """HOW FAR BELOW ITS LOWEST STORE A RUN'S SP CAN HAVE BEEN, by the listing: the most any function the screen
    manager's reading reads lowers SP by ALLOCATION — `lea -n(sp),sp`, `subq`, a `link`'s displacement — in one
    unbroken run of such instructions (the next push stores at the SP they left). What a measured depth — a run's
    lowest STORE — can be short of the truth by."""
    read = reading(blob.elf)
    bound(blob)
    return max(longest_allocation(read.functions()[name]) for name in read.functions_read() & set(read.functions()))


def longest_allocation(body):
    """The most the instructions of `body` (`[(address, text)]`) lower SP by allocation in one unbroken run."""
    most = run = 0
    for _at, text in body:
        link = aes_switch.LINK.match(text)
        allocated = -int(link.group(1)) if link else aes_switch.allocated_by(text)
        run = run + allocated if allocated > 0 else 0
        most = max(most, run)
    return most


# ---- THE STACK, A PATTERN UNDER AN EXCEPTION'S FRAME, AND THE STAGING OF OUR OWN VDI -----------------------------------------
def stack_of(image):
    """`(bottom, top)` of the screen manager's stack over `image`: off the machine's own pointers."""
    lo, top, _why = aes_gemctrl.its_stack(image)
    return lo, top


PATTERN_STEP, PATTERN_BIAS = 7, 3       # odd, so the 256 bytes of the pattern are all there before one repeats
WATCHED_UNDER_AN_EXCEPTION = 0x500      # no stack watched is longer: PD1's 1,196 bytes, a window of the run's own band
Trap = namedtuple("Trap", "taken_at under opcode")
Trap.__doc__ = """One exception taken on a watched stack: SP's depth below the stack's top where it is taken, the bytes
its handler used under that SP (the 68000's frame among them), and — for a `trap #2` — the VDI's opcode (contrl[0])."""
VDI_OPCODE_AT = aes.header_constants("gsx.h")["AES_GSX_OPCODE"]


def _untouched(at):
    """The pattern the stack under an exception's frame is laid with: a byte that tells its own address."""
    return (at * PATTERN_STEP + PATTERN_BIAS) & aes.BYTE_MASK


class _ExceptionsOn:
    """A WATCH ROUND ANOTHER (or round none) that measures every exception TAKEN ON ONE STACK (`(bottom, top)`)
    through the handler at `handler` (the ROM's `trap #2` handler; the Line-A one): at the handler's entry the
    stack under the exception's frame is laid with a pattern, and where the exception returns the lowest byte the
    handler's side stored over is read — `taken`, a `Trap` each. An exception taken on another stack (another
    process's AES call) is not its business, and every stop of the inner watch's is handed on."""

    def __init__(self, stack, inner=None, handler=aes_event.VDI_TRAP, past_its_word=0):
        self._lo, self._top = stack
        assert self._top - self._lo <= WATCHED_UNDER_AN_EXCEPTION, "the pattern would be laid over more than a stack"
        self._inner, self._armed, self._handler = inner, frozenset(inner.first) if inner else frozenset(), handler
        self._past_its_word = past_its_word     # a Line-A's frame names the word itself: its handler returns past it
        self._taken_at, self._back, self._opcode, self.taken = None, None, None, []
        self.first = self._armed | {handler}

    def stopped(self, pc, sp, memory):
        own = True
        if pc == self._handler and self._back is None and self._lo <= sp < self._top:
            self._taken_at, self._opcode = sp + EXCEPTION_FRAME_BYTES, case.word_in(memory, VDI_OPCODE_AT)
            self._back = (case.long_in(memory, sp + aes_event.EXCEPTION_FRAME_PC) + self._past_its_word) & BUS
            for at in range(self._lo, sp):
                memory[at] = _untouched(at)
        elif pc == self._back:
            lowest = next((at for at in range(self._lo, self._taken_at) if memory[at] != _untouched(at)), self._taken_at)
            assert lowest > self._lo, "the handler stored down to the watched stack's last byte: its need is not read"
            self.taken.append(Trap(self._top - self._taken_at, self._taken_at - lowest, self._opcode))
            self._back = None
        else:
            own = pc == self._handler
        if pc in self._armed:
            self._armed = frozenset(self._inner.stopped(pc, sp, memory))
        else:
            assert own, f"a run watched at its exceptions stopped at {pc:#x}: no stop of this watch's, none the inner one armed"
        return (self._armed | {self._handler} | ({self._back} if self._back else frozenset())) - {pc}


def with_our_vdi(memory, shore):
    """`memory` with the blob of `shore` laid and ITS OWN VDI under `trap #2`, as a ROM that ships links it
    (`aes_switch._our_vdi_under_the_trap`, band 4's staging: the BIOS's door staged, the blob's `vdi_rom_entry`
    and its C dispatcher behind it). `THE_ROM_S`: the machine's own VDI, nothing laid."""
    if shore != THE_ROM_S:
        blob = blob_of(shore)
        memory[blob.base:blob.base + len(blob.blob)] = blob.blob
        aes_switch._our_vdi_under_the_trap(memory, blob)
    return memory


# ---- TWO OBJECTS STAGED IN THE DESK'S MENU: an icon, and a USERDEF whose routine keeps the SP it is called at ------------------
# A LABELLED ARGUMENT-CLASS STAGING, the only one here: no process of the booted machines draws an icon or a
# USERDEF on the screen manager's stack, and the two chains the bound ends on are exactly those — an icon's blit
# under a menu's walk, an application's routine under ob_user. So ONE ITEM of the desk's View menu (its plain one)
# is made a G_ICON or a G_USERDEF, its block in this band; the ROM's (or our) screen manager then draws it by its
# own run, on its own stack. The USERDEF's routine is five instructions: it keeps the LOWEST SP it was entered at
# in a longword of the band, and answers 0 (no state left to draw).
BAND_OFFSET, BAND_BYTES = 0x3E00, 0x80        # between aes_fslib.py's band (+$3C00) and test_aes_wm_update.py's (+$3F00)
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_stack.py: an ICONBLK or a USERBLK staged in the desk's menu")
OBJECTS = aes.header_constants("objects.h")
THE_STAGED_ITEM = aes_gemctrl.VIEW_S_PLAIN_ITEM
ICON, USERDEF = "a G_ICON", "a G_USERDEF"
ICON_ROWS, ICON_WIDTH, LABEL = 8, 16, b"A\0"
BITMAP_AT, LABEL_AT = BAND_AT + OBJECTS["IB_BYTES"] + WORD_BYTES, BAND_AT + OBJECTS["IB_BYTES"] + WORD_BYTES + 2 * ICON_ROWS * WORD_BYTES
ROUTINE_AT, LOWEST_SP_AT = BAND_AT + 0x60, BAND_AT + 0x78
NEVER_CALLED = 0xFFFFFFFF
AN_ICON_S_CHARACTER = 0x1041            # ib_char: the colours and "A", as `test_aes_gemgraf_gr.py`'s icons have them
CMPA_L_ABSOLUTE_SP, BCC_PAST_THE_STORE, MOVE_L_SP_ABSOLUTE = b"\xbf\xf9", b"\x64\x06", b"\x23\xcf"
MOVEQ_0_D0 = b"\x70\x00"


def _keeps_the_lowest_sp():
    """`cmpa.l <lowest>,sp` / `bcc.s` / `move.l sp,<lowest>` / `moveq #0,d0` / `rts`."""
    lowest = struct.pack(">I", LOWEST_SP_AT)
    return CMPA_L_ABSOLUTE_SP + lowest + BCC_PAST_THE_STORE + MOVE_L_SP_ABSOLUTE + lowest + MOVEQ_0_D0 + aes_switch.RTS


def staged_in_the_menu(ram, kind):
    """The pokes that make the staged item of the desk's menu over `ram` an object of `kind` (above)."""
    item = (case.long_in(ram, aes.AES_GL_MNTREE) & BUS) + THE_STAGED_ITEM * OBJECTS["OB_BYTES"]
    type_word = struct.pack(">H", OBJECTS["G_ICON"] if kind == ICON else OBJECTS["G_USERDEF"])
    block = struct.pack(">I", BAND_AT)
    if kind == USERDEF:
        return {item + OBJECTS["OB_TYPE"]: type_word, item + OBJECTS["OB_SPEC"]: block,
                BAND_AT: struct.pack(">II", ROUTINE_AT, 0), ROUTINE_AT: _keeps_the_lowest_sp(),
                LOWEST_SP_AT: struct.pack(">I", NEVER_CALLED)}
    iconblk = bytearray(OBJECTS["IB_BYTES"])
    struct.pack_into(">III", iconblk, OBJECTS["IB_PMASK"], BITMAP_AT, BITMAP_AT + ICON_ROWS * WORD_BYTES, LABEL_AT)
    struct.pack_into(">H", iconblk, OBJECTS["IB_CHAR"], AN_ICON_S_CHARACTER)
    struct.pack_into(">4h", iconblk, OBJECTS["IB_XICON"], 0, 0, ICON_WIDTH, ICON_ROWS)
    struct.pack_into(">4h", iconblk, OBJECTS["IB_XTEXT"], ICON_WIDTH, 0, ICON_WIDTH, ICON_ROWS)
    bitmaps = struct.pack(f">{ICON_ROWS}H", *[aes.WORD_MASK] * ICON_ROWS) + struct.pack(f">{ICON_ROWS}H", *[0x5555] * ICON_ROWS)
    return {item + OBJECTS["OB_TYPE"]: type_word, item + OBJECTS["OB_SPEC"]: block, BAND_AT: bytes(iconblk),
            BITMAP_AT: bitmaps, LABEL_AT: LABEL}


# ---- THE SCENARIOS -----------------------------------------------------------------------------------------------------------
# What a hand does, twice told: `hand`, the steps a BOOTED machine is continued by from its idle (`aes_boot`:
# each a tuple of what it receives, then its run to the next idle) — the measured runs, from the screen manager's
# real entry; and `arrival` / `at_idle`, the same told as `test_aes_gemctrl.py` tells a row (the ROM's handler at its
# arrival, taken through the dispatcher) — the run whose traps are WATCHED. `staged`: the object staged in the menu.
Scenario = namedtuple("Scenario", "hand arrival at_idle staged", defaults=(None,))
A = aes_gemctrl.TWO_WINDOWS
PRESS, RELEASE, onto, click = aes_gemctrl.PRESS, aes_gemctrl.RELEASE, aes_gemctrl.onto, aes_gemctrl.click
HCTL_BUTTON, HCTL_RECT = aes_gemctrl.HCTL_BUTTON, aes_gemctrl.HCTL_RECT
AN_ELEVATOR_DRAGGED_TO, A_TITLE_DRAGGED_TO = (250, 110), (150, 60)
BUTTON_DOWN, BUTTON_UP = aes_boot.ikbd(aes_boot.LEFT_DOWN, 0, 0), aes_boot.ikbd(aes_boot.NO_BUTTON, 0, 0)
THE_VIEW_TITLE, ITS_PLAIN_ITEM = aes_event.THE_VIEW_TITLE_S_POINT, aes_event.VIEW_S_PLAIN_ITEM_S_POINT


def _held(gadget, *then):
    """A gadget of the top window pressed and held, then `then`: `(hand, arrival)`."""
    def hand():
        return ((aes_boot.mouse_to(*aes_gemctrl.gadget(A, gadget)),), (BUTTON_DOWN, aes_boot.CLICK_TICKS), *then)
    return hand, lambda: aes_gemctrl.gadget_arrival(A, gadget, PRESS, HCTL_BUTTON)


def _the_view_menu(staged=None):
    def hand():
        return ((aes_boot.mouse_to(*THE_VIEW_TITLE),), (aes_boot.mouse_to(*ITS_PLAIN_ITEM),),
                (BUTTON_DOWN, BUTTON_UP, aes_boot.CLICK_TICKS))
    return Scenario(hand, lambda: aes_gemctrl.Arrival(A, {0: (aes_event.ONTO_THE_VIEW_TITLE,)}, HCTL_RECT),
                    {0: aes_event.ONTO_ITS_PLAIN_ITEM, 1: click}, staged)


THE_ELEVATOR, THE_TITLE, THE_CLOSER = "the vertical elevator dragged", "the title dragged", "the closer held and released"
THE_MENU, THE_ICON, THE_USERDEF = "the View menu dropped, an item clicked", "...one item an icon", "...one item a USERDEF"
SCENARIOS = {
    THE_ELEVATOR: Scenario(*_held("the vertical elevator", (aes_boot.mouse_to(*AN_ELEVATOR_DRAGGED_TO),), (BUTTON_UP,)),
                           {0: onto(AN_ELEVATOR_DRAGGED_TO), 1: RELEASE}),
    THE_TITLE: Scenario(*_held("the title", (aes_boot.mouse_to(*A_TITLE_DRAGGED_TO),), (BUTTON_UP,)),
                        {0: onto(A_TITLE_DRAGGED_TO), 1: RELEASE}),
    THE_CLOSER: Scenario(*_held("the closer", (BUTTON_UP,)), {0: RELEASE}),
    THE_MENU: _the_view_menu(),
    THE_ICON: _the_view_menu(ICON),
    THE_USERDEF: _the_view_menu(USERDEF),
}
HANDLER_OF = {THE_ELEVATOR: "hctl_button", THE_TITLE: "hctl_button", THE_CLOSER: "hctl_button", THE_MENU: "hctl_rect",
              THE_ICON: "hctl_rect", THE_USERDEF: "hctl_rect"}


# ---- THE MEASURED RUNS, FROM THE SCREEN MANAGER'S REAL ENTRY ------------------------------------------------------------------
Run = namedtuple("Run", "deepest userdef_at observed")
Run.__doc__ = """One shore's run of a scenario on a booted machine: `deepest`, the bytes of PD1's stack it used (the top
less its lowest STORE, over every step); `userdef_at`, the bytes below the top at which the staged USERDEF's routine
was entered at its deepest (None: the scenario stages none); `observed`, the handlers its ctlmgr called, in order."""


@functools.cache
def _booted(shore):
    """The two-window machine, booted: the ROM's own — or the one whose screen manager is the blob's of `shore`."""
    if shore == THE_ROM_S:
        return aes_gemctrl.machine(A)
    return aes_boot.accessory_machine(*aes_gemctrl.ACCESSORY_MODES[A], ours=blob_of(shore))


@functools.cache
def measured(name, shore=THE_ROM_S):
    """THE SCENARIO `name` RUN FROM THE REAL ENTRY: the booted machine of `shore` — its screen manager parked in
    its own ctlmgr's wait, at the top of its own stack — continued by the scenario's hand, step by step, through
    the ROM's interrupt handlers and its own dispatcher; on our shore OUR VDI under every trap. A `Run`.
    TWO LABELLED STAGINGS are laid over the booted machine first, and it is continued as the machine they make
    (`aes_boot.restaged`): the build's own VDI linked under `trap #2` — which patches one `jsr` of the blob's own
    text, so the blob the continuation holds untouched is the blob AS STAGED — and, for the two scenarios that name
    one, the object staged in the desk's menu."""
    scenario, machine = SCENARIOS[name], _booted(shore)
    memory = with_our_vdi(machine.image(), shore)
    for at, data in (staged_in_the_menu(machine.ram, scenario.staged) if scenario.staged else {}).items():
        memory[at:at + len(data)] = data
    lo, top = stack_of(memory)
    machine = aes_boot.restaged(machine, memory)
    lowest, observed = top, []
    for received in scenario.hand():
        machine = machine.continued(*received)
        lowest = min([lowest] + [start for start, length in machine.boot.stored if lo <= start < top])
        observed += [handler for handler, _point in machine.observed]
    assert lowest < top and HANDLER_OF[name] in observed, f"{name}: the screen manager called {observed}"
    kept = machine.long(LOWEST_SP_AT) if scenario.staged == USERDEF else NEVER_CALLED
    assert (kept != NEVER_CALLED) == (scenario.staged == USERDEF), f"{name}: the staged routine kept {kept:#x}"
    return Run(top - lowest, top - kept if scenario.staged == USERDEF else None, tuple(observed))


# ---- WHAT THE OS NEEDS UNDER A TRAP, BY THE VDI CALL — AND UNDER A LINE-A TRAP ----------------------------------------------
def _watched_from_its_frame(pokes, entry, inner, shore, handler=aes_event.VDI_TRAP, past_its_word=0):
    """The ROM's routine at `entry` over `pokes` (its frame staged) on the run's own stack, watched at the
    exceptions it takes through `handler` — the VDI of `shore` under its traps: the `Trap`s."""
    memory = with_our_vdi(make_image(pokes), shore)
    watch = _ExceptionsOn((emu.STACK_TOP - WATCHED_UNDER_AN_EXCEPTION, emu.STACK_TOP), inner, handler, past_its_word)
    rom_bench.watched_original(memory, entry, watch)
    rom_bench.vet_the_run_just_made(f"the ROM's run of {entry:#x}, watched at its exceptions")
    return tuple(watch.taken)


def _row_of(routine, arguments, pokes, at_idle):
    """A handler's call as the row that switches it is (`aes_event.woken_row`): what settles it from the ROM's runs."""
    return aes_event.woken_row("", routine, arguments, lambda: pokes, at_idle, objects=True, answered=False)


@derived.kept
def _traps_taken(routine, arguments, pokes, at_idle, shore, blob_s_bytes):
    """THE DERIVATION: the ROM's handler `addrs.<routine>` from its arrival `pokes`, taken through the deliveries of
    its own scheduled run, watched at its `trap #2`s — the VDI under them the ROM's, or the blob's of `shore`
    (`blob_s_bytes`: its content, which keys the answer — the one thing of the build this run executes)."""
    del blob_s_bytes
    row = _row_of(routine, arguments, pokes, at_idle)
    settled, entry = aes_switching.settled(row), getattr(addrs, routine)
    inner = aes_switching.the_rom_s(settled.switches, entry)
    taken = _watched_from_its_frame(settled.pokes, entry, inner, shore)
    inner.vet_ended(f"the ROM's run of {routine}, watched at its traps")
    return taken


def _content_of(shore):
    return b"" if shore == THE_ROM_S else bytes(blob_of(shore).blob)


@functools.cache
def traps_of(name, shore=THE_ROM_S):
    """Every `trap #2` the ROM's handler takes in the scenario `name`, the VDI of `shore` under it: `Trap`s."""
    scenario = SCENARIOS[name]
    arrived = aes_gemctrl.at(scenario.arrival())
    pokes = case.merge_pokes(arrived.pokes, staged_in_the_menu(make_image(arrived.pokes), scenario.staged) if scenario.staged else {})
    return _traps_taken(arrived.name, arrived.arguments, pokes, scenario.at_idle, shore, _content_of(shore))


def os_needs(shore=THE_ROM_S):
    """THE MOST THE OS USES UNDER A `trap #2`, BY THE VDI's OPCODE — the AES's trap handler, the BIOS's door, the
    VDI's entry and the function called — over every trap of every scenario, with the VDI of `shore` under the
    trap: `{opcode: bytes}`."""
    needs = {}
    for name in SCENARIOS:
        for trap in traps_of(name, shore):
            needs[trap.opcode] = max(needs.get(trap.opcode, 0), trap.under)
    return needs


def under_a_trap(shore=THE_ROM_S):
    """...and the most under any: what the bound charges under its deepest trap."""
    return max(os_needs(shore).values())


@derived.kept
def line_a_need():
    """THE DERIVATION (ROM-only): what the `$a000` in gsx_mfsave takes of the stack it is met on — the 68000's
    exception frame and the Line-A dispatcher's own pushes — by the ROM's gsx_mfsave watched at the Line-A handler.
    (The build's own dispatcher, `src/vdi`'s `linea_rom_dispatch`, is the ROM's instructions: the same frames.)"""
    handler = case.long_in(make_image(aes_gsx.machine()), addrs.VECTOR_LINE_A) & BUS
    # ...a routine of no argument: the machine as it is, nothing staged at the first argument's place.
    taken = _watched_from_its_frame(aes_gsx.machine(), addrs.AES_ROM_GSX_MFSAVE, None, THE_ROM_S, handler, WORD_BYTES)
    assert len(taken) == 1, f"gsx_mfsave takes {len(taken)} Line-A traps: one was expected"
    return taken[0].under


# ---- THE INTERRUPTS' NEST ----------------------------------------------------------------------------------------------------
# `aes_switch.worst_interrupt_need` is a vertical blank with an MFP interrupt inside it (band 4's, for the
# dispatcher's stack). ON TOP OF IT, A HORIZONTAL BLANK: its handler (`src/bios/isr.S`, isr_hbl_entry — the ROM's
# seven instructions) runs at level 2 with the 68000's frame and D0's word on the interrupted stack, raises the
# INTERRUPTED code's mask to 3 and returns; it raises nothing of its own, so a vertical blank (level 4) is taken
# INSIDE it at any of its instructions, and an MFP interrupt inside that. It is taken at all only over code at
# level 0 or 1 — which a process's is after `aes_rom_sti` (`andi.w #$f8ff,sr`) — and then once, until the next
# `sti`. Nothing in the code makes the three-deep nest impossible; it is charged.
def hbl_need(shore=THE_ROM_S):
    """The bytes of the interrupted stack the horizontal blank's handler uses: the ROM's from its vector, or the
    entry of the blob of `shore` — MEASURED, as `aes_switch` measures the other three."""
    image = make_image(aes_switch.cursor_shown(aes_event.machine()))
    if shore == THE_ROM_S:
        return aes_switch._interrupt_entered(image, case.long_in(image, addrs.VECTOR_HBL) & BUS)
    blob = blob_of(shore)
    image[blob.base:blob.base + len(blob.blob)] = blob.blob
    return aes_switch._interrupt_entered(image, blob.entry("isr_hbl_entry"))


@functools.cache
def nest(shore=THE_ROM_S):
    """THE WORST NEST OF INTERRUPTS on a stack whose code runs with the mask open: a horizontal blank, a vertical
    blank inside it, the deeper MFP handler inside that — the ROM's handlers', or the build's own entries'."""
    needs = aes_switch.interrupt_needs() if shore == THE_ROM_S else aes_switch.our_interrupt_needs(blob_of(shore))
    return hbl_need(shore) + aes_switch.worst_interrupt_need(needs)


def need(blob):
    """`(the bytes of its stack the screen manager can need on blob, at its deepest trap — else in its own code)`:
    the bound, OUR VDI's need under a trap and the worst nest of the build's own interrupt entries on top."""
    read, shore = bound(blob), shore_of(blob)
    at_a_trap = read.at_a_trap + under_a_trap(shore)
    return max(read.deepest, at_a_trap) + nest(shore), at_a_trap > read.deepest


# ---- dsptch's COST, MEASURED: the leaf's declaration held to a run -----------------------------------------------------------
def dsptch_measured(shore):
    """The bytes the dsptch of the blob of `shore` stores below the SP it is called at before it leaves for the
    dispatcher's stack: run over a machine whose screen manager is RUNNING (a scenario's arrival: the ready list's
    head, the guard clear), at an SP in the dead middle of its stack, to the instruction after disp's `jsr` of
    savestate."""
    blob = blob_of(shore)
    memory = make_image(aes_gemctrl.at(SCENARIOS[THE_CLOSER].arrival()).pokes)
    memory[blob.base:blob.base + len(blob.blob)] = blob.blob
    lo, top = stack_of(memory)
    sp = (lo + top) // 2 & ~1
    assert not memory[aes.AES_INDISP] and case.long_in(memory, aes.AES_RLR) & BUS == SCREEN_MANAGER, "the premise: it runs"
    disp = aes_switch.listed_functions(blob.elf)["aes_rom_disp"]
    after_savestate = next(after for (_at, text), (after, _next) in zip(disp, disp[1:]) if "<aes_rom_savestate>" in text)
    emu.install_chip_seeds()
    try:
        emu.run_bench(memory, blob.entry("aes_dsptch"), 0, sp, emu.SENTINEL, door={after_savestate},
                      seed_regs=rom_bench.entry_registers())
        assert emu.bench_door_pc() == after_savestate, "dsptch did not reach disp's loop"
    finally:
        emu.bench_abort()
    writes, _truncated = emu.bench_writes(memory)
    return sp - min(at for at in writes if lo <= at < sp)


# ---- THE REPORT (`python test/aes_stack.py`) -------------------------------------------------------------------------------
LIMITS = ("LIMITS: a measured depth is a run's lowest STORE (SP may have stood up to `untouched` lower); no interrupt "
          "is taken at a run's deepest point (the nest is added by arithmetic).")


def _chain(chain):
    return " > ".join(f"{function} {held}" for function, held in chain)


def report():
    lo, top = stack_of(_booted(THE_ROM_S).image())
    span = top - lo
    lines = [f"PD1's stack: [{lo:#x}, {top:#x}) = {span} bytes. The ROM beside ours: the OS under a trap #2 by opcode "
             f"{dict(sorted(os_needs().items()))}; nest {nest()} (hbl {hbl_need()}); Line-A $a000 takes {line_a_need()}",
             LIMITS]
    for shore in BLOBS:
        blob, name = blob_of(shore), shore
        read, needed = bound(blob), need(blob)[0]
        userdef, path = at_the_userdef_call(blob)
        ours_at, the_rom_s_at = measured(THE_USERDEF, shore).userdef_at, measured(THE_USERDEF).userdef_at
        lines += [f"{name}: entered at {', '.join(read.entered_at)} (+{read.allowed} allowed)",
                  f"  OWN FRAMES {read.deepest}: {_chain(read.chain)}",
                  f"    + nest {nest(shore)} (hbl {hbl_need(shore)}) = {read.deepest + nest(shore)} of {span}: "
                  f"{span - read.deepest - nest(shore)} spare",
                  f"  DEEPEST TRAP at {read.at_a_trap}: {_chain(read.trap_chain)}",
                  f"    + OUR VDI under a trap {under_a_trap(shore)} (by opcode {dict(sorted(os_needs(shore).items()))}) "
                  f"+ nest {nest(shore)} = {needed} of {span}: OVER by {needed - span}" if needed > span else
                  f"    + OUR VDI under a trap {under_a_trap(shore)} + nest {nest(shore)} = {needed} of {span}: {span - needed} spare",
                  f"  AN APPLICATION'S ROUTINE (a USERDEF's) is entered {userdef} down ({' > '.join(path)}): {span - userdef} "
                  f"bytes left, {span - userdef - nest(shore)} with the nest; measured {ours_at} against the ROM's "
                  f"{the_rom_s_at}: {ours_at - the_rom_s_at} bytes less than under the ROM",
                  f"  dsptch takes {reading(blob.elf).of('aes_dsptch').deepest} (measured {dsptch_measured(shore)}); "
                  f"untouched at most {untouched_at_most(blob)}"]
    lines.append("MEASURED from the real entry, the lowest store on PD1's stack (the ROM's machine / ours, our VDI under the traps):")
    for scenario in SCENARIOS:
        ours = ", ".join(f"{shore} {measured(scenario, shore).deepest} (+ nest {nest(shore)} = "
                         f"{measured(scenario, shore).deepest + nest(shore)})" for shore in BLOBS)
        lines.append(f"  {scenario}: the ROM's {measured(scenario).deepest}; {ours}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
