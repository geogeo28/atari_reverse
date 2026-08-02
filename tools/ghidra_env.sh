#!/bin/bash
# Locate Ghidra and a JDK 21, for the five headless entry points to source:
#   headless.sh · reapply.sh · dump_names.sh · load_dump.sh · hw_scan.sh
#
# Both are overridable from the environment, so this works off a Homebrew macOS box:
#   GHIDRA_HOME=/opt/ghidra JAVA_HOME=/usr/lib/jvm/java-21 bash tools/headless.sh ...
#
# The defaults glob Homebrew's Cellar rather than pinning a version, so a `brew upgrade
# ghidra` doesn't break every script. Sets $GHIDRA and exports $JAVA_HOME.

GHIDRA="${GHIDRA_HOME:-$(ls -d /opt/homebrew/Cellar/ghidra/*/libexec 2>/dev/null | tail -1)}"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}"

if [ ! -x "${GHIDRA:-}/support/analyzeHeadless" ]; then
    echo "error: Ghidra not found${GHIDRA:+ at $GHIDRA}." >&2
    echo "       Set GHIDRA_HOME to your Ghidra install — the directory containing" >&2
    echo "       support/analyzeHeadless (Homebrew: /opt/homebrew/Cellar/ghidra/<version>/libexec)." >&2
    exit 1
fi

if [ ! -x "$JAVA_HOME/bin/java" ]; then
    echo "error: no JDK at JAVA_HOME=$JAVA_HOME." >&2
    echo "       Ghidra 12 needs Java 21; set JAVA_HOME to your JDK (Homebrew: openjdk@21 is keg-only)." >&2
    exit 1
fi
