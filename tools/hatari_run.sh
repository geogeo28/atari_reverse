#!/bin/bash
# Launch a game in Hatari for dynamic analysis (run the depacker, then dump memory).
#   hatari_run.sh <game_dir> [autostart] [parse_file]
#     game_dir    host folder mounted as drive C: (e.g. projects/<name>/bin)
#     autostart   program to auto-run, e.g. C:\START.TOS   (optional)
#     parse_file  debugger command file for --parse (optional; implies --debug)
#
# In the running emulator, enter the debugger with AltGr+Pause (macOS: Fn/Right-Alt+
# Pause, or set a key via the GUI). Then dump the depacked image, e.g.:
#     savebin dump.bin 0 0x100000        # whole 1MB — carve in Ghidra
# or, once you know the program's text base/size:
#     savebin dump.bin $<base> $<len>
# then:  load_dump.sh <proj_dir> <name> dump.bin 0x<base> 0x<entry>
set -euo pipefail

# TOS ROM: yours via $TOS_IMG, else the one Hatari ships (Homebrew path, version-globbed).
# TOS ROMs are Atari copyright and are not distributed with this repo.
TOS="${TOS_IMG:-$(find /opt/homebrew/Cellar/hatari -name tos.img 2>/dev/null | head -1)}"
[ -r "${TOS:-}" ] || { echo "error: no TOS ROM found; set TOS_IMG to a TOS image file." >&2; exit 1; }

GAMEDIR="$1"; AUTO="${2:-}"; PARSE="${3:-}"

ARGS=(--tos "$TOS" --memsize 1 --monitor rgb --tos-res low --harddrive "$GAMEDIR")
[ -n "$AUTO" ] && ARGS+=(--auto "$AUTO")
[ -n "$PARSE" ] && ARGS+=(--parse "$PARSE" --debug)

echo "hatari ${ARGS[*]}"
exec hatari "${ARGS[@]}"