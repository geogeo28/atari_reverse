"""`test/opcodes.py`'s words that the `.S` files spell too, held equal to `include/m68k_encodings.h` — the two cannot
import each other, so the header's macro is expanded by the C preprocessor and the word compared."""
import subprocess
from pathlib import Path

import opcodes

INCLUDE = Path(__file__).resolve().parents[1] / "include"


def expanded(expression):
    """`expression` over `m68k_encodings.h`'s macros, as the preprocessor expands it: an integer."""
    source = f'#include "m68k_encodings.h"\n{expression}\n'
    text = subprocess.run(["cc", "-E", "-P", "-x", "c", f"-I{INCLUDE}", "-"], input=source, capture_output=True,
                          text=True, check=True).stdout
    return int(eval(text.strip(), {"__builtins__": {}}))     # the header's arithmetic, and nothing else


def test_cmp_w_immediate_d0_is_the_header_s_word():
    assert opcodes.CMP_W_IMMEDIATE_D0 == expanded("M68K_CMP_W_IMMEDIATE(M68K_D0)")
