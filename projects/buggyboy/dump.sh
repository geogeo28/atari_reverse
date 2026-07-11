#!/bin/bash
# Dump current DB names to out/names_dump.txt (recover GUI edits). Then:
#   diff <(grep -E '^(fn|var|cmt) ' names.txt | sort) <(grep -E '^(fn|var|cmt) ' out/names_dump.txt | sort)
# and merge anything new into names.txt.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../../tools/dump_names.sh" "$HERE/ghidra_proj" BuggyBoy BUGGYBOY.PRG "$HERE/out/names_dump.txt"