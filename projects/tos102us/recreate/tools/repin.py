"""usage: repin.py <the recorder's .jsonl> <recreate/> [--apply] — EVERY CYCLE PIN A RECORDED RUN MOVED, RE-DERIVED
from that run (`tools/pin_recorder.py` made the record; recreate/README.md, "Re-pinning the rows that switch").

A pin is spelt `(a, b)` in a test file — the whole run's `(the ROM's, ours)` by blob, a price's `(ours, the ROM's)`
— and the record holds, for each one that moved, the row, the pair the test held and the pair the run measured.
The measured pair replaces the old one IN THE FILE OF THE TEST THAT RECORDED IT — or, where that file does not spell
it, in the test modules it imports (`test_tier3.py` holds rows whose pins are their own batteries') — and nowhere
else; the ratio a `Priced(...)` line quotes in its trailing comment is made again from the line's own pairs.

REFUSED, each by name, and nothing of that pair is written:
  * A RECORD WHOSE ROM-SIDE MEMBER MOVED. A re-pin absorbs what OUR build's change did to OUR count; the ROM's count
    of a row moves only if the row's machine or its deliveries did — a regression of the harness, never a re-pin's.
  * an old pair the records move two ways (two rows that share a pair and part: a blind replace would pin one with
    the other's);
  * a pair neither the recording test's file nor a test module it imports spells (a pin asserted another way): a
    hand's. A file that happens to spell the same pair for a row no test of it recorded is never touched;
  * A PAIR SPELT MORE TIMES THAN ROWS RECORDED ITS MOVE. Two rows that share a pair are two spellings; when only one
    of them moved, the other line is a row nobody recorded, and no text says which is which: a hand's, both.
THE SCREEN MANAGER'S TURNS (a record of kind "turn": the turns of our ctlmgr inside a row's run on a blob) are not
pairs in a test's file but lines of ONE DATA FILE, `test/aes_turns_pinned.py`, keyed by the row and the blob: the
row's line for the blob is written (or added, for a row the file did not hold) from the record — REFUSED where the
ROM's own member of a turn moved, or where the run makes another number of turns than the line holds (a window
appeared or went: the row's machine changed). THE ACCESSORIES' TURNS (kind "accessory turn") are the same, in
`test/aes_accessory_turns_pinned.py`, AND THE DESK'S (kind "desk turn"; band 6's binding) in `test/aes_desk_turns_pinned.py`.
A RECORD OF ANY OF THEM WHOSE DATA FILE IS MISSING is refused by the row's name
and the run ends non-zero: nothing is dropped in silence.
A price whose CALLS or WINDOWS moved is not a pair move and is printed for a hand. Prints what it did; writes
nothing without --apply. Run the suite again afterwards: what it could not reach is what is still red.
"""
import ast
import collections
import json
import pathlib
import re
import sys

WHOLE, PRICED = "whole", "priced"       # the recorder's two kinds: a whole run's cycles on a blob; the table's price
TURN = "turn"                           # ...and a third: the screen manager's turns inside a run on a blob (one data file)
TURNS_FILE = "aes_turns_pinned.py"
ACCESSORY_TURN = "accessory turn"       # ...and a fourth: the accessories' turns, behind our door (a data file of the same shape)
ACCESSORY_TURNS_FILE = "aes_accessory_turns_pinned.py"
DESK_TURN = "desk turn"                 # ...and a fifth: the desk's, the ROM's text over our AES (band 6's binding; the same shape)
DESK_TURNS_FILE = "aes_desk_turns_pinned.py"
TURNS_FILES = {TURN: TURNS_FILE, ACCESSORY_TURN: ACCESSORY_TURNS_FILE, DESK_TURN: DESK_TURNS_FILE}
A_TURNS_ROW = re.compile(r'^    (?P<row>".*"): \{$')       # the data file's lines: a row opens its blobs' ...
A_TURNS_BLOB = re.compile(r'^        "(?P<blob>\w+)": (?P<turns>\(.*\)),$')         # ...one line a blob...
A_TURNS_ROW_ENDS = "    },"             # ...and closes
THE_ROM_S_MEMBER_OF_A_TURN = 1          # a turn is (ours, the ROM's, our thunks')
THE_ROM_S_MEMBER = {WHOLE: 0, PRICED: 1}                 # which of a pair is the ROM's own count
THE_DATA_FILE_IS_MISSING = "THE DATA FILE IS MISSING"
REFUSALS_THAT_FAIL_THE_RUN = ("THE ROM'S OWN COUNT MOVED", THE_DATA_FILE_IS_MISSING)       # `main` ends non-zero on either
A_RATIO_COMMENT = re.compile(r"(#\s*)(\d\.\d\d)( / (\d\.\d\d))?(\s*)$")
A_PAIR = re.compile(r"\((\d+), (\d+)\)")
A_PRICE_S_PAIRS = 2                     # own, the caller's own: the first two fields of a `Priced`

Move = collections.namedtuple("Move", "kind who old new file blob")
Move.__doc__ = """One pair a record moves: its `kind`, the row (`who`: its registered name), the pair held and measured,
the `file` of the test that recorded it, and — a whole run's — the `blob` it was measured on ("" for a price)."""
AN_IMPORTED_TEST_MODULE = re.compile(r"^\s*(?:import|from) (test_\w+)", re.MULTILINE)
Outcome = collections.namedtuple("Outcome", "rewritten refused by_hand texts")
Outcome.__doc__ = """What a re-pin would do: `rewritten`, `{file name: pairs replaced}`; `refused`, `[(why, Move)]`; `by_hand`,
the records that are no pair move; `texts`, `{path: the file's new text}` for the files that change."""


class RomSideMoved(ValueError):
    """A record's ROM-side count is not the one the test held."""


def _spelt(pair):
    return f"({pair[0]}, {pair[1]})"


def _where_it_may_be_spelt(file, texts):
    """The paths a pin recorded by a test of `file` may live in: that file, then the test modules it imports."""
    by_name = {path.name: path for path in texts}
    if file not in by_name:
        return []
    imported = [f"{module}.py" for module in AN_IMPORTED_TEST_MODULE.findall(texts[by_name[file]])]
    return [by_name[file]] + [by_name[name] for name in imported if name in by_name]


def moves_of(records):
    """`([Move], [the records that are no pair move])` of the recorder's `records` (dicts)."""
    moves, by_hand = [], []
    for record in records:
        if record["kind"] == WHOLE:
            moves.append(Move(WHOLE, record["who"][0], tuple(record["old"]), tuple(record["new"]), record.get("file", ""),
                              record["who"][1]))
        elif record["kind"] == PRICED:
            held, measured = record["old"], record["new"]
            if held[A_PRICE_S_PAIRS:] != measured[A_PRICE_S_PAIRS:] or any(
                    (old is None) != (new is None) for old, new in zip(held[:A_PRICE_S_PAIRS], measured[:A_PRICE_S_PAIRS])):
                by_hand.append(record)
            moves += [Move(PRICED, record["who"], tuple(old), tuple(new), record.get("file", ""), "")
                      for old, new in zip(held[:A_PRICE_S_PAIRS], measured[:A_PRICE_S_PAIRS])
                      if old is not None and new is not None and tuple(old) != tuple(new)]
        elif record["kind"] not in TURNS_FILES:    # (a turn's record is its data file's: `turns_repinned`)
            by_hand.append(record)
    return moves, by_hand


def _turns_spelt(turns):
    return "(" + "".join(f"({', '.join(str(count) for count in turn)}), " for turn in turns).rstrip(" ") + ")"


def _turns_held(lines):
    """`{(row, blob): the turns as the data file spells them}` of the file's `lines`."""
    held, row = {}, None
    for line in lines:
        opens, blob = A_TURNS_ROW.match(line), A_TURNS_BLOB.match(line)
        if opens:
            row = json.loads(opens["row"])
        elif blob and row is not None:
            held[row, blob["blob"]] = blob["turns"]
        elif line == A_TURNS_ROW_ENDS:
            row = None
    return held


def _turns_read(spelt):
    """A line's turns (`_turns_spelt`'s spelling) as lists: what a record's `old` and `new` are."""
    return [list(turn) for turn in ast.literal_eval(spelt)]


def turns_repinned(records, text, kind=TURN):
    """THE DATA FILE'S RE-PIN (`TURNS_FILES[kind]`: its `text`) by the records of that `kind`: `(the new text, how many
    lines were written, [why each refused record was])`. A line is its row's and its blob's: written from the record,
    or added for a row the file did not hold. A RECORD IS HELD TO WHAT THE FILE HOLDS, not to its own `old` (a record
    made in another copy of the tree, or before a hand edit, is not this file's): REFUSED, its line left, where its
    `old` is not the file's line (none, for a row the file holds; a line, for one it does not), and where THE ROM'S
    MEMBER of any turn — or the number of turns — is not the file's. A record that changes nothing writes nothing."""
    lines = text.split("\n")
    held = _turns_held(lines)
    written, refused = 0, []
    for record in (each for each in records if each["kind"] == kind):
        (row, blob), old, new = record["who"], [list(turn) for turn in record["old"]], [list(turn) for turn in record["new"]]
        in_the_file = _turns_read(held[row, blob]) if (row, blob) in held else []
        if old != in_the_file:
            refused.append(f"{row} on {blob}: THE RECORD WAS NOT MADE AGAINST THIS FILE — it says the line held {old} "
                           f"and the file holds {in_the_file or 'no line for it'}: record the run again over this tree")
            continue
        its_own = [turn[THE_ROM_S_MEMBER_OF_A_TURN] for turn in in_the_file], [turn[THE_ROM_S_MEMBER_OF_A_TURN] for turn in new]
        if in_the_file and its_own[0] != its_own[1]:
            refused.append(f"{row} on {blob}: THE ROM'S OWN COUNT MOVED in its turns ({kind}), {its_own[0]} -> "
                           f"{its_own[1]} — the row's machine or its deliveries changed: no re-pin absorbs that")
            continue
        if new and new != in_the_file:
            held[row, blob] = _turns_spelt(new)
            written += 1
    opening = next(index for index, line in enumerate(lines) if line.startswith("PINNED = {"))
    closing = next(index for index, line in enumerate(lines) if index > opening and line == "}")
    body = []
    for row in sorted({row for row, _blob in held}):
        body.append(f"    {json.dumps(row, ensure_ascii=False)}: {{")
        body += [f'        "{blob}": {held[row, blob]},' for each, blob in sorted(held) if each == row]
        body.append(A_TURNS_ROW_ENDS)
    return "\n".join(lines[:opening + 1] + body + lines[closing:]), written, refused


def vet(move):
    """`move` moves OUR member alone — or `RomSideMoved`, by the row's name."""
    member = THE_ROM_S_MEMBER[move.kind]
    if move.old[member] != move.new[member]:
        raise RomSideMoved(f"{move.who}: THE ROM'S OWN COUNT MOVED, {move.old[member]} -> {move.new[member]} "
                           f"({move.kind}: {_spelt(move.old)} -> {_spelt(move.new)}) — the row's machine or its "
                           f"deliveries changed: no re-pin absorbs that")


def _requoted(line):
    """`line` with the ratio (or two) its trailing comment quotes made again from the pairs it spells."""
    comment = A_RATIO_COMMENT.search(line)
    pairs = A_PAIR.findall(line[:comment.start()]) if comment else []
    if not comment or "Priced(" not in line or not pairs:
        return line
    ratios = [f"{int(ours) / int(the_rom_s):.2f}" for ours, the_rom_s in pairs[:A_PRICE_S_PAIRS]]
    quoted = f"{ratios[0]} / {ratios[1]}" if comment.group(3) and len(ratios) == A_PRICE_S_PAIRS else ratios[0]
    return line[:comment.start()] + f"{comment.group(1)}{quoted}{comment.group(5)}"


def repinned(records, texts):
    """THE RE-PIN of `texts` (`{path: text}`: the test files) by `records`: an `Outcome`."""
    moves, by_hand = moves_of(records)
    refused, sound = [], []
    for move in moves:
        try:
            vet(move)
            sound.append(move)
        except RomSideMoved as moved:
            refused.append((str(moved), move))
    measured, rows, files = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
    recorded = collections.defaultdict(set)
    for move in sound:
        measured[move.old].add(move.new)
        rows[move.old].add(move.who)
        files[move.old].add(move.file)
        recorded[move.old].add((move.who, move.blob))
    texts, rewritten = dict(texts), collections.Counter()
    for old, news in sorted(measured.items()):
        witness = next(move for move in sound if move.old == old)
        if len(news) > 1:
            refused.append((f"{_spelt(old)} is moved two ways, to {sorted(news)}, by {sorted(rows[old])[:3]}", witness))
            continue
        (new,) = news
        spelling = [next((path for path in _where_it_may_be_spelt(file, texts) if _spelt(old) in texts[path]), None)
                    for file in sorted(files[old])]
        if None in spelling:
            refused.append((f"neither a test's file ({sorted(files[old])}) nor a test module it imports spells "
                            f"{_spelt(old)} for {sorted(rows[old])[0]!r}", witness))
            continue
        spelt = sum(texts[path].count(_spelt(old)) for path in dict.fromkeys(spelling))
        if spelt > len(recorded[old]):
            refused.append((f"{_spelt(old)} is spelt {spelt} times in {sorted({path.name for path in spelling})} and "
                            f"{len(recorded[old])} row(s) recorded its move ({sorted(rows[old])[:3]}): another line is a row "
                            f"nobody recorded, and nothing says which", witness))
            continue
        for path in dict.fromkeys(spelling):
            lines = texts[path].split("\n")
            for index, line in enumerate(lines):
                if _spelt(old) in line:
                    rewritten[path.name] += line.count(_spelt(old))
                    lines[index] = _requoted(line.replace(_spelt(old), _spelt(new)))
            texts[path] = "\n".join(lines)
    return Outcome(dict(rewritten), refused, by_hand, texts)


def main(arguments):
    record_path, root = pathlib.Path(arguments[0]), pathlib.Path(arguments[1])
    records = [json.loads(line) for line in record_path.read_text().splitlines() if line]
    before = {path: path.read_text() for path in sorted((root / "test").glob("*.py"))}
    outcome = repinned(records, before)
    turns_written, turns_refused = 0, []
    for kind, name in TURNS_FILES.items():
        turns_path = root / "test" / name
        if turns_path not in outcome.texts:
            # ...REFUSED BY NAME, never dropped: a record of a kind whose data file is not there is a pin nobody wrote
            turns_refused += [f"{record['who'][0]} on {record['who'][1]}: {THE_DATA_FILE_IS_MISSING} — `{name}` is not in "
                              f"{root / 'test'}, and its record ({kind}) is written nowhere"
                              for record in records if record["kind"] == kind]
            continue
        outcome.texts[turns_path], written, refused = turns_repinned(records, outcome.texts[turns_path], kind)
        turns_written, turns_refused = turns_written + written, turns_refused + refused
    print(f"{len(records)} records: {sum(outcome.rewritten.values())} pair(s) re-pinned in {len(outcome.rewritten)} file(s), "
          f"{turns_written} line(s) of turns written (the screen manager's, the accessories', the desk's), "
          f"{len(outcome.refused) + len(turns_refused)} refused, {len(outcome.by_hand)} for a hand")
    for name, count in sorted(outcome.rewritten.items()):
        print(f"  {name}: {count} pair(s)")
    for why in [why for why, _move in outcome.refused] + turns_refused:
        print(f"  REFUSED: {why}")
    for record in outcome.by_hand:
        print(f"  BY HAND: {record['who']}: {record['old']} -> {record['new']}")
    if "--apply" in arguments:
        for path, text in outcome.texts.items():
            if text != before[path]:
                path.write_text(text)
    said = [why for why, _move in outcome.refused] + turns_refused
    return 1 if any(failing in why for why in said for failing in REFUSALS_THAT_FAIL_THE_RUN) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
