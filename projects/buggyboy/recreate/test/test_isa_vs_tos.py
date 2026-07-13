"""Cross-validate the Musashi oracle against Hatari's independent (WinUAE-derived) 68000 core.

Runs oracle/isa_conformance.py's catalog of self-contained instruction snippets on both cores and
asserts they agree on the exact instruction mix BuggyBoy uses (byte/word memory RMW, shifts, ext,
muls/divs, addx, cmp+scc). Two independent, hardware-validated cores agreeing is the evidence that
"verified against Musashi" means "verified against a real 68000". Only the *defined* CCR bits are
compared (e.g. N/Z after a DIVS/DIVU overflow are officially undefined and excluded).

Skips when Hatari or a TOS ROM isn't installed (the ROM isn't redistributable).
"""
import pytest

import harness            # noqa: F401  — inserts oracle/ onto sys.path
import isa_conformance as isa

pytestmark = pytest.mark.skipif(
    not isa.tos_probe.available(),
    reason="ISA cross-check needs Hatari + a TOS ROM (see oracle/isa_conformance.py)")


def test_musashi_matches_real_68000():
    mismatches, total = isa.compare()
    assert not mismatches, (
        f"{len(mismatches)}/{total} instruction cases diverge between Musashi and a real 68000:\n"
        + "\n".join(f"  {name}: musashi=(res={m[0]:#010x} ccr={m[1]:#04x}) "
                    f"hatari=(res={h[0]:#010x} ccr={h[1]:#04x})" for name, m, h in mismatches[:20]))
