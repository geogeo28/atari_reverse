"""Pin every constant atari/bench.py and atari/verify.py re-type from the platform C.

WHAT DRIFTS. plat.h is the ONE definition the platform C and the platform asm share, but a Python
harness cannot include a C header: bench.py and verify.py re-type the handful of values they need
(the ledger's address and shape, the timer reload, the screen and window geometry, the page-zero
addresses the teardown check dumps). Nothing but this file makes the two copies move together.

WHY IT MATTERS. It has already bitten this directory once: the ledger's fixed address moved from
0x80000 to 0xC0000 in the C and bench.py's copy did not, so the harness `savebin`ed a window of
zeros out of the machine and reported a failure the target did not have. That is the whole failure
mode — a stale harness constant never says "I am stale", it accuses the target, or worse reports
one field's bytes as another field's timing.

HOW. Every expected value is PARSED from the C (atari/plat.h, atari/main.c, and the engine's
include/game_consts.h, which is where the screen geometry plat.h restates is actually defined) and
never re-typed here: a third copy would be a third thing to drift. The Python side is read by
IMPORTING bench and verify and looking at their module-level constants — both keep all their work
behind main() and functions, so importing them runs nothing (verified: the import only pulls in
numpy/PIL and resolves paths).

A constant this file was asked to pin but could not parse REFUSES loudly, because a pin that
silently skips is worse than no pin at all.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_INCLUDE = HERE.parent / "include"

if str(HERE) not in sys.path:                   # verify.py does a plain `import bench`
    sys.path.insert(0, str(HERE))

import bench                                    # noqa: E402  (path set up above)
import verify                                   # noqa: E402

PLAT_H = HERE / "plat.h"
MAIN_C = HERE / "main.c"
GAME_CONSTS_H = ENGINE_INCLUDE / "game_consts.h"
C_SOURCES = (PLAT_H, MAIN_C, GAME_CONSTS_H)


# ---------------------------------------------------------------- a small #define parser -------
# Only what these headers actually contain: object-like #defines whose bodies are integer literals
# (optionally hex, optionally U/L suffixed) and arithmetic over #defines already resolved.
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT_RE = re.compile(r"//[^\n]*")
CONTINUATION_RE = re.compile(r"\\\n")
DEFINE_RE = re.compile(r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)[ \t]+(.*)$", re.M)
TOKEN_RE = re.compile(r"[A-Za-z_]\w*|0[xX][0-9a-fA-F]+[uUlL]*|\d+[uUlL]*|<<|>>|[-+*/%&|^~()]|\s+")
INTEGER_RE = re.compile(r"(0[xX][0-9a-fA-F]+|\d+)[uUlL]*\Z")
OPERATORS = frozenset(("<<", ">>", "+", "-", "*", "/", "%", "&", "|", "^", "~", "(", ")"))
INTEGER_SUFFIXES = "uUlL"


def strip_comments(text):
    return LINE_COMMENT_RE.sub("", BLOCK_COMMENT_RE.sub(" ", text))


def tokenize(expression):
    """The expression's tokens, or None if it contains anything outside the whitelist above."""
    tokens, position = [], 0
    for match in TOKEN_RE.finditer(expression):
        if match.start() != position:
            return None
        position = match.end()
        token = match.group().strip()
        if token:
            tokens.append(token)
    return tokens if position == len(expression) else None


def evaluate(expression, resolved):
    """The C value of `expression`, or None if it is not integer arithmetic over `resolved`.

    Every token is checked against the whitelist before anything is evaluated, so the eval below
    sees only integers, resolved names' values and C operators. `/` becomes `//`: C truncates
    toward zero and Python floors, which agree because every value in these headers is >= 0."""
    tokens = tokenize(expression)
    if tokens is None:
        return None
    terms = []
    for token in tokens:
        if token in OPERATORS:
            terms.append("//" if token == "/" else token)
        elif INTEGER_RE.fullmatch(token):
            terms.append(token.rstrip(INTEGER_SUFFIXES))
        elif token in resolved:
            terms.append(str(resolved[token]))
        else:
            return None
    try:
        value = eval(" ".join(terms), {"__builtins__": {}}, {})
    except (SyntaxError, ZeroDivisionError, TypeError, ValueError):
        return None
    return value if isinstance(value, int) else None


def collect_define_bodies(paths):
    """Every object-like #define body in `paths`, refusing a name defined twice differently."""
    bodies = {}
    for path in paths:
        text = CONTINUATION_RE.sub(" ", strip_comments(path.read_text()))
        for name, body in DEFINE_RE.findall(text):
            body = body.strip()
            previous = bodies.get(name)
            if previous is not None and previous != body:
                raise AssertionError(f"{name} is defined twice in {[p.name for p in paths]} "
                                     f"as {previous!r} and {body!r}; this parser has one namespace")
            bodies[name] = body
    return bodies


def resolve_defines(bodies):
    """Values for the bodies that are integer arithmetic, resolving names until a fixed point."""
    pending, resolved = dict(bodies), {}
    while True:
        progressed = False
        for name, body in list(pending.items()):
            value = evaluate(body, resolved)
            if value is None:
                continue
            resolved[name] = value
            del pending[name]
            progressed = True
        if not progressed:
            return resolved


C_DEFINES = resolve_defines(collect_define_bodies(C_SOURCES))
MAIN_C_TEXT = strip_comments(MAIN_C.read_text())


def c_define(name):
    """One parsed C constant. REFUSES loudly rather than letting a pin skip itself."""
    if name not in C_DEFINES:
        sources = ", ".join(str(path) for path in C_SOURCES)
        raise AssertionError(f"{name} could not be parsed out of {sources} — this file cannot "
                             f"check the harness constant that copies it, so the pin refuses "
                             f"instead of silently passing")
    return C_DEFINES[name]


# ---------------------------------------------------------------- shapes stated in main.c -------
STAGE_NAMES_RE = re.compile(r"STAGE_NAMES\s*\[\s*BI_STAGES\s*\]\s*=\s*\{([^{}]*)\}", re.S)
STAGE_ENTRY_RE = re.compile(r"\[\s*(STAGE_\w+)\s*\]\s*=\s*\"([^\"]*)\"")
PASS_STRIDE_RE = re.compile(r"_Static_assert\s*\(\s*sizeof\s*\(\s*BiPassLedger\s*\)\s*=="
                            r"\s*(\d+)\s*\+\s*BI_STAGES\s*\*\s*(\d+)\s*,")
# `[^{}]*` and not `.*?`: a lazy body would start at the FIRST typedef struct in main.c and
# run all the way down to this one, swallowing every struct in between.
LEDGER_STRUCT_RE = re.compile(r"typedef\s+struct\s*\{([^{}]*)\}\s*BiLedger\s*;", re.S)
LEDGER_LONG_FIELD_RE = re.compile(r"unsigned\s+long\s+([A-Za-z_]\w*)")


def c_stage_names():
    """main.c's STAGE_NAMES, ordered by the STAGE_* index each entry is designated with."""
    block = STAGE_NAMES_RE.search(MAIN_C_TEXT)
    if block is None:
        raise AssertionError(f"no STAGE_NAMES[BI_STAGES] initializer in {MAIN_C} — the stage list "
                             f"this file pins bench.STAGES against cannot be read")
    by_index = {c_define(symbol): name for symbol, name in STAGE_ENTRY_RE.findall(block.group(1))}
    if sorted(by_index) != list(range(len(by_index))):
        raise AssertionError(f"main.c's STAGE_NAMES indices are {sorted(by_index)}, not a dense "
                             f"0..n range — the published stage order cannot be read")
    return tuple(by_index[index] for index in range(len(by_index)))


def c_pass_stride_terms():
    """(header bytes, bytes per stage) out of main.c's own assertion on the pass record's size."""
    match = PASS_STRIDE_RE.search(MAIN_C_TEXT)
    if match is None:
        raise AssertionError(f"no `_Static_assert(sizeof(BiPassLedger) == N + BI_STAGES * M)` in "
                             f"{MAIN_C} — the stride bench.py parses with cannot be checked")
    return int(match.group(1)), int(match.group(2))


def c_ledger_header_fields():
    """The BiLedger header: its leading run of `unsigned long` scalars, in declaration order."""
    struct = LEDGER_STRUCT_RE.search(MAIN_C_TEXT)
    if struct is None:
        raise AssertionError(f"no `typedef struct {{...}} BiLedger;` in {MAIN_C} — the header "
                             f"layout bench.HEADER_FIELDS names cannot be read")
    fields = []
    for member in struct.group(1).split(";"):
        match = LEDGER_LONG_FIELD_RE.fullmatch(" ".join(member.split()))
        if match is None:
            break
        fields.append(match.group(1))
    if not fields:
        raise AssertionError(f"BiLedger in {MAIN_C} starts with no `unsigned long` field")
    return tuple(fields)


def c_pixel_doubling():
    """plat.h states the view's vertical doubling as VIEW_ROW_BYTES == that many screen lines."""
    return c_define("VIEW_ROW_BYTES") // c_define("PLAT_SCREEN_BYTES_PER_LINE")


# ---------------------------------------------------------------- the pins ----------------------
BITS_PER_BYTE = 8
TEARDOWN_REGION_ADDRESSES = {label: address for label, address, _size, _why in verify.TEARDOWN_REGIONS}


def shown(value):
    return f"{value} (={value:#x})" if isinstance(value, int) else repr(value)


def assert_matches_c(where, value, c_name):
    expected = c_define(c_name)
    assert value == expected, (f"{where} is {shown(value)} but the C's {c_name} is "
                               f"{shown(expected)} — the harness has drifted from the target")


def test_ledger_identity_matches_plat_h():
    assert_matches_c("bench.LEDGER_ADDR", bench.LEDGER_ADDR, "BI_LEDGER_ADDR")
    assert_matches_c("bench.LEDGER_MAGIC", bench.LEDGER_MAGIC, "BI_LEDGER_MAGIC")
    assert_matches_c("bench.LEDGER_VERSION", bench.LEDGER_VERSION, "BI_LEDGER_VERSION")
    assert_matches_c("bench.CAPTURE_BYTES", bench.CAPTURE_BYTES, "BI_LEDGER_CAPTURE_BYTES")


def test_ledger_header_fields_match_the_c_struct():
    """bench.HEADER_BYTES is derived from this tuple, so pinning the names pins the size too."""
    expected = c_ledger_header_fields()
    assert tuple(bench.HEADER_FIELDS) == expected, (
        f"bench.HEADER_FIELDS is {bench.HEADER_FIELDS} but main.c's BiLedger header is {expected} "
        f"— the harness would read each field's bytes under another field's name")


def test_ledger_pass_record_layout_matches_the_c():
    assert_matches_c("bench.PASS_NAME_BYTES", bench.PASS_NAME_BYTES, "BI_LEDGER_NAME_BYTES")
    assert_matches_c("bench.PASS_FIELDS_OFFSET", bench.PASS_FIELDS_OFFSET, "BI_LEDGER_NAME_BYTES")
    header_bytes, stage_bytes = c_pass_stride_terms()
    assert bench.PASS_HEADER_BYTES == header_bytes, (
        f"bench.PASS_HEADER_BYTES is {bench.PASS_HEADER_BYTES} but main.c's pass record asserts "
        f"{header_bytes} bytes before its stage triples")
    assert bench.STAGE_TRIPLE_BYTES == stage_bytes, (
        f"bench.STAGE_TRIPLE_BYTES is {bench.STAGE_TRIPLE_BYTES} but main.c's pass record asserts "
        f"{stage_bytes} bytes per stage")
    stride = header_bytes + c_define("BI_STAGES") * stage_bytes
    assert bench.PASS_BYTES == stride, (
        f"bench.PASS_BYTES is {bench.PASS_BYTES} but main.c's BiPassLedger stride is {stride} "
        f"({header_bytes} + BI_STAGES * {stage_bytes}) — every pass after the first would be "
        f"read at the wrong offset")


def test_stage_list_matches_main_c():
    expected = c_stage_names()
    assert_matches_c("len(bench.STAGES)", len(bench.STAGES), "BI_STAGES")
    assert tuple(bench.STAGES) == expected, (
        f"bench.STAGES is {bench.STAGES} but main.c publishes {expected} — the table's stage "
        f"columns would silently slide")


def test_timer_c_reload_matches_plat_h():
    assert_matches_c("bench.TIMER_C_RELOAD", bench.TIMER_C_RELOAD, "TIMER_C_RELOAD")


def test_timer_tick_ns_is_read_from_the_target_not_retyped():
    """plat.h's TIMER_TICK_NS reaches the harness through the ledger's own tick_ns field, so there
    is no Python copy to pin — but a copy appearing later must be pinned, not left to drift."""
    tick_ns = c_define("TIMER_TICK_NS")
    assert "tick_ns" in bench.HEADER_FIELDS, (
        f"bench.HEADER_FIELDS no longer names tick_ns, so plat.h's TIMER_TICK_NS ({tick_ns}) no "
        f"longer reaches the harness from the target — it must be pinned here instead")
    for module in (bench, verify):
        assert not hasattr(module, "TIMER_TICK_NS"), (
            f"{module.__name__}.py now re-types TIMER_TICK_NS; pin it here against plat.h's "
            f"{tick_ns} rather than leaving a second copy to drift")


def test_render_window_matches_the_c():
    assert_matches_c("bench.RENDER_COLUMNS_HIGH", bench.RENDER_COLUMNS_HIGH, "PLAT_COLUMNS_HIGH")
    assert_matches_c("bench.RENDER_COLUMNS_LOW", bench.RENDER_COLUMNS_LOW, "PLAT_COLUMNS_LOW")
    assert_matches_c("bench.SCREEN_WINDOW_LINES", bench.SCREEN_WINDOW_LINES, "SCREEN_WINDOW_LINES")
    assert_matches_c("verify.WINDOW_LINES", verify.WINDOW_LINES, "SCREEN_WINDOW_LINES")
    assert_matches_c("verify.HUD_LINES", verify.HUD_LINES, "SCREEN_HUD_LINES")
    doubled = c_define("PLAT_RENDER_H") * c_pixel_doubling()
    assert bench.SCREEN_WINDOW_LINES == doubled, (
        f"bench.SCREEN_WINDOW_LINES is {bench.SCREEN_WINDOW_LINES} but plat.h's PLAT_RENDER_H "
        f"pixel-doubled is {doubled} screen lines")


def test_screen_geometry_matches_the_c():
    assert_matches_c("bench.SCREEN_W", bench.SCREEN_W, "SCREEN_W")
    assert_matches_c("bench.SCREEN_H", bench.SCREEN_H, "SCREEN_H")


def test_screen_pixels_agree_with_the_platform_byte_geometry():
    """bench.py counts the screen in pixels (it crops Hatari's screenshot); plat.h counts it in
    bytes for the asm. A change to either side that does not reach the other lands here."""
    bytes_per_line = c_define("PLAT_SCREEN_BYTES_PER_LINE")
    planes = c_define("SCREEN_PLANES")
    line_bytes = bench.SCREEN_W // BITS_PER_BYTE * planes
    assert line_bytes == bytes_per_line, (
        f"bench.SCREEN_W ({bench.SCREEN_W}) over {planes} planes is {line_bytes} bytes a line but "
        f"plat.h's PLAT_SCREEN_BYTES_PER_LINE is {bytes_per_line}")
    screen_bytes = bench.SCREEN_H * bytes_per_line
    assert screen_bytes == c_define("PLAT_SCREEN_BYTES"), (
        f"bench.SCREEN_H ({bench.SCREEN_H}) lines of {bytes_per_line} bytes is {screen_bytes} but "
        f"plat.h's PLAT_SCREEN_BYTES is {c_define('PLAT_SCREEN_BYTES')}")


def test_page_zero_addresses_match_plat_h():
    assert_matches_c("verify.V_BAS_AD_ADDR", verify.V_BAS_AD_ADDR, "V_BAS_AD_ADDR")
    assert_matches_c("verify.NVBLS_ADDR", verify.NVBLS_ADDR, "NVBLS_ADDR")
    assert_matches_c("verify.VBLQUEUE_ADDR", verify.VBLQUEUE_ADDR, "VBLQUEUE_ADDR")


def test_teardown_palette_region_matches_plat_h():
    palette = TEARDOWN_REGION_ADDRESSES["palette"]
    assert_matches_c("verify.TEARDOWN_REGIONS['palette']", palette, "PALETTE_ADDR")


def test_no_game_cue_uses_the_drum_priority():
    """DESIGN's DMA mixer takes the LOWEST priority number as the most important, and the VBL hands
    the song's drum lane YM_DRUM_PRIORITY on every hit.  If a game cue were ever authored at that
    same number the drums would preempt it (or it them) on a tie, so the reservation is a rule the
    bank has to keep and not a convention the audio pass remembers."""
    ids = (HERE.parent / "audio" / "blackice_sfx_ids.h").read_text()
    drum_priority = int(re.search(r"#define\s+YM_DRUM_PRIORITY\s+(\d+)",
                                  (HERE.parent / "audio" / "ym_music.h").read_text()).group(1))
    priorities = re.search(r"blackice_sfx_priority\[[^\]]*\]\s*=\s*\{([^}]*)\}", ids).group(1)
    cue_priorities = [int(value) for value in priorities.replace(" ", "").split(",") if value]
    assert cue_priorities, "blackice_sfx_ids.h names no cue priorities — the pin parsed nothing"
    assert min(cue_priorities) > drum_priority, (
        f"a game cue is authored at priority {min(cue_priorities)}, which is the drum lane's "
        f"reserved YM_DRUM_PRIORITY ({drum_priority})")
