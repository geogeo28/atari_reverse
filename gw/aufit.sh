#!/usr/bin/env bash
#
# Launch Aufit (flux -> Pasti/STX with weak-bit + track-image support) on a flux
# image, under Wine. Aufit is the tool for a *protected* disk: unlike hxcfe's
# sector-only STX (see README "Known limitation"), it writes the full track
# images a Copylock samples, so the exported STX actually boots.
#
# Aufit is an interactive WPF app — it opens a window; it cannot convert headless.
# This script only sets the environment and opens it on your flux file; you drive
# the load -> inspect -> export in the GUI (steps printed on launch).

set -euo pipefail

readonly WINE="/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine"
readonly AUFIT_DIR="/Users/geogeo/opt/Aufit-1.3"
readonly AUFIT_EXE="Aufit.exe"

# Native .NET (the prefix has Framework 4.x) and software WPF rendering — Wine's
# Vulkan path crashes Aufit's mono runtime on this machine.
export WINEDEBUG=-all
export WINEDLLOVERRIDES="winevulkan=d;mscoree=n"

die() { echo "ERROR: $*" >&2; exit 1; }

flux="${1:-}"
[ -n "$flux" ] || die "usage: $(basename "$0") <flux-file.scp>  (also reads KryoFlux stream, etc.)"
[ -f "$flux" ] || die "no such file: $flux"
[ -x "$WINE" ] || die "Wine not found: $WINE"
[ -f "$AUFIT_DIR/$AUFIT_EXE" ] || die "Aufit not found: $AUFIT_DIR/$AUFIT_EXE"

# Wine reaches the whole filesystem through drive Z: with forward slashes.
flux_abs="$(cd "$(dirname "$flux")" && pwd)/$(basename "$flux")"
flux_win="Z:${flux_abs}"

cat <<EOF
Launching Aufit on: $flux_abs

In the Aufit window:
  1. File > Open (or drag the flux in) — it is already passed as an argument, so
     it may load on its own. If not, browse to the path above.
  2. Let it analyse all tracks. Cylinders 0-4 hold the protection (sectors 11/12,
     weak/fuzzy bits) — Aufit flags unstable sectors; that is expected, not an error.
  3. Resolve/accept the weak sectors (Aufit's whole job — it keeps the fuzzy mask
     rather than freezing one value).
  4. File > Save As / Export > Pasti (.stx). Save next to the flux.

Then verify it boots with track images (the thing hxcfe could not give):
  right-click the .stx > Run in Hatari, and confirm the log has NO
  "fdc stx : no track image for read track" lines. A clean boot = done.
EOF

cd "$AUFIT_DIR"
nohup "$WINE" "$AUFIT_EXE" "$flux_win" >/tmp/aufit_gui.log 2>&1 &
echo
echo "Aufit launched (pid $!). Window should appear shortly; output in /tmp/aufit_gui.log."
