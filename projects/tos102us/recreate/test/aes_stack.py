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
    where the trap returns — with THE BLOB'S OWN VDI under the trap for our shore, ENTRY, DISPATCHER AND HANDLERS
    (`aes_switch.vdi_table_mapping`: every slot of the ROM's opcode tables mapped to the blob's handler, and
    `who_ran` holds that it is the one entered — for a pass the staging stopped at the dispatcher and every "need
    of our VDI" was the ROM's handlers' + 32), the ROM's for the ROM's. A need is a lowest STORE; the verdict
    charges the bound on SP: the largest allocation nothing stores under that a run of the opcode reaches — in the
    blob's own handlers AND ITS OWN RASTER ENGINES, which the staging maps the Line-A vectors to
    (`unstored_under`, `needs_bounded`). ITS PRECONDITION: the workstation's attributes as the AES leaves them.
    AND CHARGED CALL BY CALL (`trap_sites`, `at_its_traps`; the frame diet, 2026-10-10): each trap site of the
    paths — a call that names its VDI opcode, read off the listing or declared for its function — carries its own
    call's need, the worst need of all where neither says; every opcode a site can ask is measured.
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

THE GATE IS THE SHIPPED BLOB'S BOUND (the program); the bench blob links the C twins of raster cores the ROM ships
as its own instructions, and its figure is printed and pinned beside it, gating nothing.

WHAT IS NOT READ HERE (wave 3, ruling W2-R5): a process that enters the AES by `trap #2` runs the opcode switch,
whose jump table the reading refuses by name — no path read here goes through it (held by a test).
"""
import collections
import functools
import re
import struct
from collections import namedtuple

import derived
from harness import addrs, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_boot
import aes_event
import aes_evinput
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


class _ArrivalsAt:
    """A WATCH ROUND ANOTHER (or round none) that COUNTS THE ARRIVALS at `places` (PCs), each by the VDI opcode the
    AES's contrl names where it is made — which call of the VDI the code there runs under: `arrived`,
    `{(opcode, place): times}`. A place is armed again at the next stop of any kind — AND EVERY `trap #2` IS A STOP
    of this watch's own, so a place reached under one call is armed for the next whatever lies between (a count is
    still "at least": twice under one call, with no stop between, is once)."""

    def __init__(self, places, inner=None, trap=aes_event.VDI_TRAP):
        self._places, self._inner, self._trap = frozenset(places), inner, trap
        self._armed = frozenset(inner.first) if inner else frozenset()
        assert not (self._places | {trap}) & self._armed, "a place counted is a stop of the watch inside: one PC, two meanings"
        assert trap not in self._places, "the trap's own handler is no place to count: it is where the places are armed again"
        self.arrived = collections.Counter()
        self.first = self._armed | self._places | {trap}

    def stopped(self, pc, sp, memory):
        if pc in self._places:
            self.arrived[case.word_in(memory, VDI_OPCODE_AT), pc] += 1
        elif pc in self._armed:
            self._armed = frozenset(self._inner.stopped(pc, sp, memory))
        else:
            assert pc == self._trap, f"a run counted at its arrivals stopped at {pc:#x}: no place of this watch's, none the inner one armed"
        return (self._armed | self._places | {self._trap}) - {pc}


def with_our_vdi(memory, shore):
    """`memory` with the blob of `shore` laid and ITS OWN VDI under `trap #2`, as a ROM that ships links it
    (`aes_switch._our_vdi_under_the_trap`: the BIOS's door staged, the blob's `vdi_rom_entry` and its C dispatcher
    behind it — AND THE DISPATCHER'S TABLES MAPPED TO THE BLOB'S OWN HANDLERS, a declared mapping: without it the
    ROM's handlers run behind our dispatcher). `THE_ROM_S`: the machine's own VDI, nothing laid."""
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
    mapped = () if shore == THE_ROM_S else tuple((slot, LONG_BYTES) for slot in aes_switch.vdi_table_slots().values())
    machine = aes_boot.restaged(machine, memory, mapped)
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


# THE CALLS NO SCENARIO'S HANDLER TAKES ON ITS OWN STACK, each by the ROM's own routine over a machine that makes it
# take them (the frame diet, 2026-10-10: the bound charges each trap ITS call's need, so every call the screen
# manager's paths can make has to be measured — `test_aes_stack.py` holds that none is missing):
#   forker, the mouse moved onto the bar .......... mchange asks the VDI where the mouse is (vq_mouse)
#   forker, a recording played back ............... mchange puts the mouse (vsin_mode, vsm_locator)
#   gsx_attr, a line colour the cache has not ..... vsl_color (the scenarios' own set the text's)
A_LINE, A_MODE_NOT_CACHED, A_COLOUR_NOT_CACHED = 0, 3, 5
THE_ROUTINES_BESIDE = {
    "forker, the mouse moved onto the bar": lambda: ("AES_ROM_FORKER", (), aes_switch.a_delay_run_out_and_the_mouse_on_the_bar()),
    "forker, a recording played back": lambda: ("AES_ROM_FORKER", (), aes_evinput.at("the desk plays a move back", aes_evinput.FORKER, 1).machine),
    "gsx_attr, a line colour the cache has not": lambda: ("AES_ROM_GSX_ATTR", (A_LINE, A_MODE_NOT_CACHED, A_COLOUR_NOT_CACHED), aes_gsx.machine()),
}


@derived.kept
def _traps_of_a_routine(routine, arguments, pokes, shore, blob_s_bytes):
    """THE DERIVATION: the ROM's routine `addrs.<routine>` over `pokes`, its frame of `arguments` staged, on the
    run's own stack, watched at its `trap #2`s — the VDI under them the ROM's, or the blob's of `shore`
    (`blob_s_bytes`: its content, which keys the answer)."""
    del blob_s_bytes
    staged = aes.staged(routine, arguments, pokes) if arguments else pokes
    return _watched_from_its_frame(staged, getattr(addrs, routine), None, shore)


@functools.cache
def traps_beside(name, shore=THE_ROM_S):
    """Every `trap #2` the routine `name` of THE_ROUTINES_BESIDE takes, the VDI of `shore` under it: `Trap`s."""
    routine, arguments, pokes = THE_ROUTINES_BESIDE[name]()
    return _traps_of_a_routine(routine, arguments, pokes, shore, _content_of(shore))


@functools.cache
def os_needs(shore=THE_ROM_S):
    """THE MOST THE OS USES UNDER A `trap #2`, BY THE VDI's OPCODE — the AES's trap handler, the BIOS's door, the
    VDI's entry and the function called — over every trap of every scenario and of the routines beside them, with
    the VDI of `shore` under the trap: `{opcode: bytes}`."""
    needs = {}
    taken = [trap for name in SCENARIOS for trap in traps_of(name, shore)]
    for trap in taken + [trap for name in THE_ROUTINES_BESIDE for trap in traps_beside(name, shore)]:
        needs[trap.opcode] = max(needs.get(trap.opcode, 0), trap.under)
    return needs


def under_a_trap(shore=THE_ROM_S):
    """...and the most under any: what the coarse sum charges under its deepest trap."""
    return max(needs_bounded(shore).values())


# ---- WHO RAN UNDER THE TRAP, AND HOW FAR SP CAN HAVE STOOD BELOW THE LOWEST STORE THERE -------------------------------------
# TWO THINGS A NEED MEASURED AS A LOWEST STORE DOES NOT SAY (the frame diet's review, 2026-10-10), each answered by
# the same runs made again with the oracle stopped at PLACES and the arrivals counted by the opcode they are under:
#   * WHOSE HANDLER RAN. `who_ran`: the blob's own handler for the opcode entered, and the ROM's — the ROM table's
#     own entry — NOT entered. (For a wave the staging stopped at the dispatcher, and every "need of our VDI" was the
#     ROM's handler's plus the dispatcher's frame; a v_gtext 100 bytes deeper in the build moved no number.)
#   * AN ALLOCATION NOTHING STORED UNDER. A function that lowers SP and does not at once store there (`lea -76(sp),sp`
#     and then a load: the blit's frame of locals) may never write its frame's bottom — the lowest store is then
#     ABOVE the lowest SP by up to that allocation. `unstored_runs` reads every such run off the listing (39 on
#     each blob; the VDI's: the blit's 76, the line's and the fill's 20); `unstored_under` is the
#     largest whose instruction was REACHED under each opcode, and `needs_bounded` adds it to the store: THE BOUND
#     the verdict charges. WHAT IT DOES NOT BOUND, said beside the numbers: code of the machine under our handlers
#     (the BIOS under `trap #13` — vq_key_s, vsm_string, vsm_locator — and the vectors an application or the
#     machine owns: USER_TIM / BUT / MOT / CUR; the LINE-A DRAWING vectors are the blob's own engines, mapped), and the
#     ROM's own VDI on the ROM's shore, whose needs stay lowest stores.
# THE PRECONDITION OF EVERY NEED HERE (the same review): THE WORKSTATION'S ATTRIBUTES ARE WHAT THE AES LEAVES THEM.
# The scenarios draw as the AES draws — its two fonts, no text effect, lines one pixel wide with no arrow ends — and
# a need holds for those. An APPLICATION that sets an effect or a line width on the physical workstation deepens the
# text's blit and the polyline under the AES's next call on that handle (measured by the review on the ROM's
# handlers: outlined text +8, a line nine wide +114, arrow ends +214) — on the ROM's own stack by as much.
A_STOP_SET_AT_MOST = 40                 # places counted in one run: the oracle's door holds 64 stops, a scenario's own among them
# WHAT THE UNSTORED READER KNOWS, AND REFUSES (the third pass's review: it PASSED OVER what it did not know, where the
# rest of the reading refuses):
#   * AN ALLOCATION is `lea -n(sp),sp`, `subq #n,sp` — and a `link` ON ANY ADDRESS REGISTER (`link a5,#-84` is
#     TextBlt's frame: read as none while only A6's was known);
#   * IT IS STORED UNDER when, DOWN THE STRAIGHT LINE from it, something is stored at or below the SP it left — a
#     push, a `pea`, a call, a store to `(sp)` — before the line is LEFT: a branch, a jump, a return, a trap, or SP
#     raised. (TextBlt's `link a5,#-84 / clr.w -82(a5) / movem.l …,-(sp)`: stored.) Every instruction on that line is
#     read by the stack reading's own `stack_effect`, which REFUSES BY NAME one it does not know;
#   * EVERY INSTRUCTION OF THE LISTING IS SCANNED, whatever labels it: a body the symbol table does not size, the
#     displaced C cores past their symbol's end on the shipped blob, a name listed twice — a run of the listing
#     broken where the addresses are (`listed_runs`). An allocation in dead code costs a stop nothing reaches.
_AN_ALLOCATING_LINK = re.compile(r"^linkw? %(?:a[0-6]|fp),#(-?\d+)$")
_STORES_AT_OR_UNDER_SP = re.compile(r"^(?:jsr|bsr\w*|pea) |.*%sp@-$|^movem?[bwl] .*,%sp@$|^clr[bwl] %sp@$")
# ...objdump's own spellings of what leaves a straight line (a conditional branch may: the path past it is another's).
_LEAVES_THE_LINE = re.compile(r"^(?:b(?:ra|hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)[swl]?|db\w+|jmp|rts|rte|rtr|trap\w*|stop|illegal|unlk) ?")


def _allocated_by(text):
    """The bytes one instruction lowers SP by WITHOUT storing where it leaves it: a `link`'s displacement on any
    address register (its push of the register is a store ABOVE them), `lea -n(sp),sp`, `subq #n,sp`; else 0."""
    link = _AN_ALLOCATING_LINK.match(text)
    return -int(link.group(1)) if link else aes_switch.allocated_by(text)


def _stored_under_down_the_line(following):
    """Whether, of the instructions `following` an allocation (texts, in the listing's order), one stores at or below
    the SP it left BEFORE the straight line is left. REFUSED, by `aes_switch.stack_effect`: an instruction the stack
    reading does not know."""
    for text in following:
        if _STORES_AT_OR_UNDER_SP.match(text):
            return True
        if _LEAVES_THE_LINE.match(text) or aes_switch.stack_effect(text) < 0:
            return False
    return False


def unstored_runs(body):
    """`{the address of the last instruction of the run: bytes}` for every unbroken run of instructions of `body`
    (`[(address, text)]`) that lower SP by ALLOCATION with nothing stored under the SP they leave down the straight
    line that follows (above)."""
    found, run = {}, 0
    for index, (at, text) in enumerate(body):
        allocated = _allocated_by(text)
        if allocated <= 0:
            run = 0
            continue
        run += allocated
        if index + 1 < len(body) and _allocated_by(body[index + 1][1]) > 0:
            continue
        if not _stored_under_down_the_line(text for _at, text in body[index + 1:]):
            found[at] = run
        run = 0
    return found


def listed_runs(listing):
    """EVERY INSTRUCTION `listing` holds, as runs of consecutive lines — `[[(address, text)]]`, a new run at every
    label and wherever the text between two instructions is not one: whatever a symbol sizes or does not."""
    runs, run = [], []
    for line in listing.splitlines():
        listed = aes_switch.LISTED_LINE.match(line)
        if listed:
            run.append((int(listed.group(1), 16), listed.group(2).strip()))
        elif run:
            runs.append(run)
            run = []
    return runs + ([run] if run else [])


@functools.cache
def unstored_allocations(elf):
    """...over EVERY instruction of the blob at `elf`: whatever runs under a trap is among them."""
    return {at: allocated for run in listed_runs(transcription.listing(elf)) for at, allocated in unstored_runs(run).items()}


def _arrivals_from_its_frame(pokes, entry, inner, shore, places):
    memory = with_our_vdi(make_image(pokes), shore)
    counting = _ArrivalsAt(places, inner)
    rom_bench.watched_original(memory, entry, counting)
    rom_bench.vet_the_run_just_made(f"the ROM's run of {entry:#x}, counted at {len(places)} places")
    return tuple(sorted((opcode, place, times) for (opcode, place), times in counting.arrived.items()))


@derived.kept
def _arrivals_in_a_scenario(routine, arguments, pokes, at_idle, shore, blob_s_bytes, places):
    """THE DERIVATION: `_traps_taken`'s run, counted at `places` instead of watched at its traps."""
    del blob_s_bytes
    settled, entry = aes_switching.settled(_row_of(routine, arguments, pokes, at_idle)), getattr(addrs, routine)
    inner = aes_switching.the_rom_s(settled.switches, entry)
    arrived = _arrivals_from_its_frame(settled.pokes, entry, inner, shore, places)
    inner.vet_ended(f"the ROM's run of {routine}, counted at its arrivals")
    return arrived


@derived.kept
def _arrivals_in_a_routine(routine, arguments, pokes, shore, blob_s_bytes, places):
    """THE DERIVATION: `_traps_of_a_routine`'s run, counted at `places`."""
    del blob_s_bytes
    staged = aes.staged(routine, arguments, pokes) if arguments else pokes
    return _arrivals_from_its_frame(staged, getattr(addrs, routine), None, shore, places)


@functools.cache
def arrivals(places, shore):
    """`{(opcode, place): times}` over every run the needs are measured by — each scenario, each routine beside
    them — with the VDI of `shore` under the traps: where the code under each VDI call went. `places`: a sorted tuple."""
    arrived = collections.Counter()
    for first in range(0, len(places), A_STOP_SET_AT_MOST):
        some = places[first:first + A_STOP_SET_AT_MOST]
        for name, scenario in SCENARIOS.items():
            at = aes_gemctrl.at(scenario.arrival())
            pokes = case.merge_pokes(at.pokes, staged_in_the_menu(make_image(at.pokes), scenario.staged) if scenario.staged else {})
            counted = _arrivals_in_a_scenario(at.name, at.arguments, pokes, scenario.at_idle, shore, _content_of(shore), some)
            arrived.update({(opcode, place): times for opcode, place, times in counted})
        for name, made in THE_ROUTINES_BESIDE.items():
            routine, arguments, pokes = made()
            counted = _arrivals_in_a_routine(routine, arguments, pokes, shore, _content_of(shore), some)
            arrived.update({(opcode, place): times for opcode, place, times in counted})
    return arrived


A_HANDLER_S_OPCODE = re.compile(r"^VDI_ROM_(\w+)_OPCODE$")


def the_handlers_named_for(opcode, elf):
    """`{symbol: entry}` of the handlers the blob at `elf` links UNDER THE NAME `include/addrs.h` gives `opcode`
    (`VDI_ROM_<NAME>_OPCODE`: `vdi_<name>`, and `vdi_rom_<name>` where its `.S` ships) — READ OFF THE SYMBOL TABLE BY
    THE OPCODE'S OWN NAME, not off the mapping the staging lays (which goes slot -> the ROM's address -> a name): a
    mapping that answers one opcode with another's handler is entered at a place this does not name."""
    names = [found.group(1).lower() for name in dir(addrs) if (found := A_HANDLER_S_OPCODE.match(name)) and getattr(addrs, name) == opcode]
    assert names, f"`include/addrs.h` names no VDI_ROM_<NAME>_OPCODE for opcode {opcode}: whose handler answers it is not known"
    wanted = {prefix + name for name in names for prefix in (aes_switch.OUR_HANDLER_S_PREFIX, aes_switch.A_TRANSCRIBED_ENTRY_S_PREFIX)}
    found = {symbol.name: symbol.start for symbol in transcription.symbol_table(elf) if symbol.kind in "TtW" and symbol.name in wanted}
    assert found, f"the blob {elf} links none of {sorted(wanted)} for VDI opcode {opcode}"
    return found


def who_ran(shore):
    """`{opcode: (times the blob's own handler was entered, times the ROM's was)}` for every opcode a need is
    measured for, under the VDI of `shore` — on a blob's shore the first is at least 1 and the second 0, or the
    need is not our VDI's; on the ROM's, the reverse. The blob's handler is the one of THE OPCODE'S NAME
    (`the_handlers_named_for`); the ROM's, what its own table holds."""
    priced = sorted(os_needs(shore))
    the_rom_s = {opcode: case.long_in(aes_switch.BASE_IMAGE, aes_switch.vdi_table_slots()[opcode]) & BUS for opcode in priced}
    ours = {} if shore == THE_ROM_S else {opcode: tuple(the_handlers_named_for(opcode, blob_of(shore).elf).values()) for opcode in priced}
    places = tuple(sorted(set(the_rom_s.values()) | {entry for entries in ours.values() for entry in entries}))
    entered = arrivals(places, shore)
    return {opcode: (sum(entered[opcode, entry] for entry in ours.get(opcode, ())), entered[opcode, the_rom_s[opcode]])
            for opcode in priced}


THE_C_TWIN_OF_AN_ENGINE = ("linea_rom_cpu_", "linea_cpu_")      # a transcribed engine's name, and its C twin's


def our_engines(elf):
    """`{entry: symbol}` of the raster engines the blob at `elf` runs AS ITS OWN: where it ships its transcriptions,
    the engines the Line-A vectors are mapped to (`aes_switch.linea_vector_mapping`: the ROM's instructions, reached
    through the vectors); where its C calls them by name, the C twin of each — both READ OFF THE SYMBOL TABLE by the
    engine's name, not off the mapping."""
    ships = elf == transcription.SHIPPED_ELF
    transcribed, twin = THE_C_TWIN_OF_AN_ENGINE
    named = {name.lower() for names in aes_switch._names_by_address().values() for name in names if name.startswith(aes_switch.AN_ENGINE_S_ROM_NAME)}
    wanted = {name if ships else twin + name[len(transcribed):] for name in named if name.startswith(transcribed)}
    return {symbol.start: symbol.name for symbol in transcription.symbol_table(elf) if symbol.kind == "T" and symbol.name in wanted}


@functools.cache
def engines_ran(shore):
    """`{opcode: (the blob's own engines entered under it — a sorted tuple of symbols —, times any engine OF THE
    ROM's was)}` over every opcode a need is measured for under the VDI of `shore`: on a blob's shore the second is
    0 for every opcode, or a text, a line, a fill or a blit under "our VDI" ran the ROM's raster code. THE ROM'S
    ENGINES are what the booted machine's ten Line-A vectors hold, the console's four among them."""
    the_rom_s = {case.long_in(aes_switch.BASE_IMAGE, vector) & BUS for vector in aes_switch.linea_vectors()}
    ours = {} if shore == THE_ROM_S else our_engines(blob_of(shore).elf)
    entered = arrivals(tuple(sorted(the_rom_s | set(ours))), shore)
    return {opcode: (tuple(sorted({ours[place] for (under, place), _times in entered.items() if under == opcode and place in ours})),
                     sum(times for (under, place), times in entered.items() if under == opcode and place in the_rom_s))
            for opcode in sorted(os_needs(shore))}


def the_largest_reached(reached, allocations, opcodes):
    """`{opcode: bytes}` over `opcodes`: THE LARGEST of `allocations` (`{place: bytes}`) among the places `reached`
    (`{(opcode, place): times}`) under each — 0 where none was. (Not the first, not the least: SP can have stood
    below the lowest store by the largest frame nothing was stored in.)"""
    under = {opcode: 0 for opcode in opcodes}
    for (opcode, place), _times in reached.items():
        under[opcode] = max(under.get(opcode, 0), allocations[place])
    return under


@functools.cache
def unstored_under(shore):
    """`{opcode: bytes}`: the largest allocation of the blob of `shore` nothing stored under (`unstored_runs`) whose
    instruction a run REACHED under that opcode's trap — how far SP can have stood below the need's lowest store."""
    allocations = unstored_allocations(blob_of(shore).elf)
    return the_largest_reached(arrivals(tuple(sorted(allocations)), shore), allocations, os_needs(shore))


@functools.cache
def needs_bounded(shore=THE_ROM_S):
    """WHAT THE VERDICT CHARGES UNDER A TRAP, by opcode: on a blob's shore the measured need (a lowest store) AND the
    largest unstored allocation reached under it — a bound on SP itself, for our own code; on the ROM's shore the
    measured need alone (its handlers' frames are not read: the limit is said beside its column)."""
    if shore == THE_ROM_S:
        return dict(os_needs(shore))
    return {opcode: need + unstored_under(shore)[opcode] for opcode, need in os_needs(shore).items()}


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


# ---- THE BOUND AT A TRAP, CALL BY CALL (ruling W2-R3, the frame diet, 2026-10-10) --------------------------------------------
# The deepest trap of the listing is a fill's and the deepest need under a trap is a text's: charged together they
# are a call no path makes. So EVERY TRAP SITE of the screen manager's paths is charged ITS OWN call's need: where
# the trap is taken (the reading's depth at the call, the door's own frames under it) plus what the OS needs under
# THAT VDI opcode. The opcode is read off the listing at the call that names it — the immediate a caller pushes for
# gsx_ncode or gsx_1code, the routines that hand their opcode on to the trap — and where the listing does not say
# (a function that fills contrl itself, a call whose argument slots are reused) it is what the function is DECLARED
# to be able to ask (held to its C source and to its listing's immediates); a site neither read nor declared is
# charged the worst need of all.
TAKES_THE_TRAP = ("aes_gsx2", "aes_rom_gsx2")
HANDS_ITS_OPCODE_ON = ("aes_gsx_ncode", "aes_gsx_1code", "aes_rom_gsx_ncode", "aes_rom_gsx_1code")
ALCYON_S_FRAME = "aes_rom_"                     # a callee of this prefix is called Alcyon's way: the opcode pushed last
OPCODES_DECLARED = {
    "aes_gsx_attr": ("VDI_ROM_VSWR_MODE_OPCODE", "VDI_ROM_VST_COLOR_OPCODE", "VDI_ROM_VSL_COLOR_OPCODE"),
    "aes_gsx_tblt": ("VDI_ROM_V_GTEXT_OPCODE",),
}
THE_SOURCE_OF = {"aes_gsx_attr": "gemgraf.c", "aes_gsx_tblt": "gemgraf.c"}
_A_PUSHED_IMMEDIATE = re.compile(r"^pea ([0-9a-f]+) <")             # objdump spells `pea (N).w` as an address
_A_PUSHED_WORD = re.compile(r"^movew #(\d+),%sp@-$")
_A_REGISTER_PUSHED = re.compile(r"^movel %(?:[ad]\d|fp),%sp@-$")
_NO_PUSH_BEFORE_THE_CALL = re.compile(r"^(?:move[lw] \S+,%sp@\(\d+\)|lea [0-9a-f]+ <\w+>,%a\d)$")
A_VDI_OPCODE_AT_MOST = 0xFF

TrapSite = namedtuple("TrapSite", "function at depth opcodes")
TrapSite.__doc__ = """One call under which a `trap #2` is taken: the `function` that makes it and the call's address;
`depth`, the deepest the trap under it is taken at, in bytes below the stack's top; `opcodes`, the VDI opcodes the
call can ask — one read off the listing, the function's declared ones, or None (neither: charged the worst)."""


_A_BRANCH_S_TARGET = re.compile(r"^(?:b[a-z]{2}[swl]?|db[a-z]{1,2}|j[a-z]{2}) ([0-9a-f]+) <")
_A_STORE_ABOVE_SP = re.compile(r"^move[lw] \S+,%sp@\((\d+)\)$")


def _refused_if_the_listing_does_not_say_one_opcode(function, body, pushed_at, index, slot_after):
    """THE TWO SHAPES A READING IN TEXT ORDER WOULD GUESS AT, REFUSED BY NAME (the frame diet's review, 2026-10-10):
    a branch of `body` that LANDS between the opcode's push (`body[pushed_at]`) and the call (`body[index]`) — two
    paths joined there, each with a push of its own: the textual one is one of two — and a STORE INTO THE OPCODE'S
    OWN SLOT after its push (`slot_after(position)`: where the slot lies from SP at that instruction)."""
    between = {at for at, _text in body[pushed_at + 1:index + 1]}
    landing = sorted(between & {int(found.group(1), 16) for _at, text in body if (found := _A_BRANCH_S_TARGET.match(text))})
    assert not landing, (
        f"{function}: a branch lands at {landing[0]:#x}, between the push that names a VDI opcode and its call at "
        f"{body[index][0]:#x} — another path reaches the call with a push of its own: the trap sites read no opcode "
        f"two paths can name (declare the function's opcodes: `OPCODES_DECLARED`)")
    for position in range(pushed_at + 1, index):
        stored = _A_STORE_ABOVE_SP.match(body[position][1])
        slot = slot_after(position)
        assert not stored or not slot <= int(stored.group(1)) < slot + LONG_BYTES, (
            f"{function}: `{body[position][1]}` at {body[position][0]:#x} stores into the slot of the VDI opcode pushed "
            f"for the call at {body[index][0]:#x}: the opcode is not the immediate pushed (declare the function's opcodes)")


def _opcode_read_at(body, index, alcyon, function="a function"):
    """THE OPCODE THE CALL AT `body[index]` NAMES, read off the instructions before it — or None. A C call of
    gsx_ncode / gsx_1code pushes the image LAST and the opcode before it (`pea (N).w`); an Alcyon one the opcode
    last, a word. Instructions that push nothing (a routine's address loaded, a store above SP) are passed over —
    and what the text's order cannot say is REFUSED, not guessed (`_refused_if_the_listing_does_not_say_one_opcode`)."""
    before = [(position, body[position][1]) for position in range(index - 1, -1, -1)
              if not _NO_PUSH_BEFORE_THE_CALL.match(body[position][1])]
    if alcyon:
        pushed = _A_PUSHED_WORD.match(before[0][1]) if before else None
        if not pushed:
            return None
        _refused_if_the_listing_does_not_say_one_opcode(function, body, before[0][0], index, lambda position: 0)
        return int(pushed.group(1))
    if len(before) < 2 or not _A_REGISTER_PUSHED.match(before[0][1]):
        return None
    pushed = _A_PUSHED_IMMEDIATE.match(before[1][1])
    if not pushed or int(pushed.group(1), 16) > A_VDI_OPCODE_AT_MOST:
        return None
    image_pushed_at = before[0][0]      # the opcode's slot: at SP until the image is pushed, a longword above it after
    _refused_if_the_listing_does_not_say_one_opcode(function, body, before[1][0], index,
                                                    lambda position: LONG_BYTES if position > image_pushed_at else 0)
    return int(pushed.group(1), 16)


def opcodes_declared(function):
    declared = OPCODES_DECLARED.get(function)
    return None if declared is None else tuple(getattr(addrs, name) for name in declared)


@functools.cache
def trap_sites(elf):
    """EVERY TRAP SITE of the screen manager's paths on the blob at `elf`: each call, by a routine that does not
    itself hand an opcode on, of one that does or of the trap's own routine — a `TrapSite` each."""
    read, (entries, allowed) = reading(elf), entered_at(elf)
    assert allowed == 0 and len(entries) == 1, "the trap sites are read from the screen manager's own entry"
    (entry,) = entries
    read.of(entry)
    sites = []
    for function in sorted(read.read_as()):
        home = function.partition(aes_switch.HANDED)[0].partition(aes_switch.INTO)[0]
        if home in TAKES_THE_TRAP + HANDS_ITS_OPCODE_ON or home not in read.functions():
            continue
        reached = (0, ()) if function == entry else read.deepest_to(entry, function)
        if reached is None:                     # read for another entry's paths (the reading is one, kept): not this one's
            continue
        above = reached[0]
        body = read.functions()[home]
        for callee, under, at in read.sites(function):
            door = callee.partition(aes_switch.INTO)[0]
            if door not in TAKES_THE_TRAP + HANDS_ITS_OPCODE_ON:
                continue
            index = next(index for index, (address, _text) in enumerate(body) if address == at)
            read_off = None if door in TAKES_THE_TRAP else _opcode_read_at(body, index, door.startswith(ALCYON_S_FRAME), home)
            sites.append(TrapSite(home, at, above + under + read.of(callee).at_a_trap,
                                  (read_off,) if read_off is not None else opcodes_declared(home)))
    return tuple(sites)


def need_under(site, shore):
    """What the OS needs under the trap of `site`: the most over the opcodes it can ask — the worst of all where
    the site says none. An opcode no run measured is refused by name."""
    needs = needs_bounded(shore)
    if site.opcodes is None:
        return max(needs.values())
    unmeasured = [opcode for opcode in site.opcodes if opcode not in needs]
    assert not unmeasured, (f"{site.function} can ask the VDI for opcode(s) {unmeasured} at {site.at:#x}, and no run "
                            f"measured what the OS needs under them (`os_needs`): add the run")
    return max(needs[opcode] for opcode in site.opcodes)


def at_its_traps(blob):
    """`(the deepest the screen manager's stack goes at a trap WITH the OS's need under it, the site)` on `blob`."""
    shore = shore_of(blob)
    site = max(trap_sites(blob.elf), key=lambda each: each.depth + need_under(each, shore))
    return site.depth + need_under(site, shore), site


def need(blob):
    """`(the bytes of its stack the screen manager can need on blob, at a trap — else in its own code)`: the deeper
    of its own frames and of its trap sites, each with its own call's need of OUR VDI under it, and the worst nest
    of the build's own interrupt entries on top."""
    read, shore = bound(blob), shore_of(blob)
    at_a_trap, _site = at_its_traps(blob)
    return max(read.deepest, at_a_trap) + nest(shore), at_a_trap > read.deepest


def need_charged_the_worst(blob):
    """...and THE COARSE SUM beside it — the deepest trap of the listing with the worst need of any call under it:
    a call no path makes, kept as what the call-by-call bound is never above."""
    return bound(blob).at_a_trap + under_a_trap(shore_of(blob)) + nest(shore_of(blob))


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


SITES_SHOWN = 6


def _worst_sites(blob):
    """The report's lines for the trap sites that need the most of `blob`'s stack, the worst first."""
    shore = shore_of(blob)
    charged = sorted({(site.depth + need_under(site, shore), site.depth, site.function, site.opcodes)
                      for site in trap_sites(blob.elf)}, reverse=True)
    return [f"    {function} at {depth}, opcode(s) {opcodes or 'unread: the worst'}: {total}"
            for total, depth, function, opcodes in charged[:SITES_SHOWN]]


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
                  f"  AT ITS TRAPS, each charged its own call's need of ITS OWN VDI, handlers and raster engines (the lowest store by "
                  f"opcode {dict(sorted(os_needs(shore).items()))}; an unstored allocation reached under it added: "
                  f"{ {opcode: under for opcode, under in sorted(unstored_under(shore).items()) if under} }):",
                  *_worst_sites(blob),
                  f"    the worst + nest {nest(shore)} = {needed} of {span}: " + (f"OVER by {needed - span}" if needed > span else
                                                                             f"{span - needed} spare")
                  + f" (the deepest trap charged the worst call's {under_a_trap(shore)}: {need_charged_the_worst(blob)})",
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
