#!/bin/bash
# Scaffold a new reverse-engineering project for an Atari ST program.
#
#   new_project.sh <name> <path-to.PRG> [base_hex] [processor]
#
# Creates projects/<name>/ with bin/ (a copy of the PRG), out/, an empty
# names.txt, and run.sh / reapply.sh wrappers wired to the generic tools.
# processor defaults to 68000:BE:32:default (use 68000:BE:32:MC68030 for 68010/020/030 code).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="$1"; PRG="$2"; BASE="${3:-0x10000}"; PROC="${4:-68000:BE:32:default}"
DEST="$HERE/../projects/$NAME"
PRGBASE="$(basename "$PRG")"

mkdir -p "$DEST/bin" "$DEST/out"
cp "$PRG" "$DEST/bin/"
touch "$DEST/names.txt"

cat > "$DEST/run.sh" <<EOF
#!/bin/bash
# Bootstrap this project (full import + analysis). Re-run wipes names; use reapply.sh after.
HERE="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$HERE/../../tools/headless.sh" "\$HERE/ghidra_proj" $NAME "\$HERE/bin/$PRGBASE" $BASE "\$HERE/decomp.c" "$PROC"
EOF

cat > "$DEST/reapply.sh" <<EOF
#!/bin/bash
# Apply names.txt to the project DB and re-export decomp.c (fast, no re-analysis).
HERE="\$(cd "\$(dirname "\$0")" && pwd)"
exec "\$HERE/../../tools/reapply.sh" "\$HERE/ghidra_proj" $NAME $PRGBASE "\$HERE/names.txt" "\$HERE/decomp.c"
EOF

chmod +x "$DEST/run.sh" "$DEST/reapply.sh"
echo "scaffolded $DEST (processor $PROC)"
echo "next: bash $DEST/run.sh   (then read decomp.c, fill names.txt, bash reapply.sh)"