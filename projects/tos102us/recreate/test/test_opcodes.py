"""`test/opcodes.py`'s words that the `.S` files spell too, held equal to `include/m68k_encodings.h` — the two cannot
import each other, so the header's macro is expanded by the C preprocessor and the word compared."""
import subprocess
from pathlib import Path

import pytest

import opcodes

INCLUDE = Path(__file__).resolve().parents[1] / "include"


def expanded(expression):
    """`expression` over `m68k_encodings.h`'s macros, as the preprocessor expands it: an integer."""
    source = f'#include "m68k_encodings.h"\n{expression}\n'
    text = subprocess.run(["cc", "-E", "-P", "-x", "c", f"-I{INCLUDE}", "-"], input=source, capture_output=True,
                          text=True, check=True).stdout
    return int(eval(text.strip(), {"__builtins__": {}}))     # the header's arithmetic, and nothing else


@pytest.mark.parametrize("word, macro", (
    (opcodes.CMP_W_IMMEDIATE_D0, "M68K_CMP_W_IMMEDIATE(M68K_D0)"),
    (opcodes.CMP_L_IMMEDIATE_D0, "M68K_CMP_L_IMMEDIATE(M68K_D0)"),
    (opcodes.MOVEA_L_IMMEDIATE_A0, "M68K_MOVEA_L_IMMEDIATE(M68K_A0)"),
    (int.from_bytes(opcodes.JSR_ABSOLUTE_LONG, "big"), "M68K_JSR_ABSOLUTE_LONG"),
    (opcodes.LINE_F, "M68K_LINE_F_WORD"),
), ids=lambda value: value if isinstance(value, str) else None)
def test_a_python_word_is_the_header_s_word(word, macro):
    assert word == expanded(macro)
