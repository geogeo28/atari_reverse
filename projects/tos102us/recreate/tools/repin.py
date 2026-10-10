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
A price whose CALLS or WINDOWS moved is not a pair move and is printed for a hand. Prints what it did; writes
nothing without --apply. Run the suite again afterwards: what it could not reach is what is still red.
"""
import collections
import json
import pathlib
import re
import sys

WHOLE, PRICED = "whole", "priced"       # the recorder's two kinds: a whole run's cycles on a blob; the table's price
THE_ROM_S_MEMBER = {WHOLE: 0, PRICED: 1}                 # which of a pair is the ROM's own count
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
        else:
            by_hand.append(record)
    return moves, by_hand


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
    print(f"{len(records)} records: {sum(outcome.rewritten.values())} pair(s) re-pinned in {len(outcome.rewritten)} file(s), "
          f"{len(outcome.refused)} refused, {len(outcome.by_hand)} for a hand")
    for name, count in sorted(outcome.rewritten.items()):
        print(f"  {name}: {count} pair(s)")
    for why, _move in outcome.refused:
        print(f"  REFUSED: {why}")
    for record in outcome.by_hand:
        print(f"  BY HAND: {record['who']}: {record['old']} -> {record['new']}")
    if "--apply" in arguments:
        for path, text in outcome.texts.items():
            if text != before[path]:
                path.write_text(text)
    return 1 if any("THE ROM'S OWN COUNT MOVED" in why for why, _move in outcome.refused) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
