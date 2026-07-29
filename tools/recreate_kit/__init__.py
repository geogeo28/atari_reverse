"""recreate_kit — the game-agnostic differential-harness machinery.

A `projects/<game>/recreate/` tree supplies the game-specific parts (its `src/`, `include/`,
`test/test_*.py` and a `project.toml`); everything shared — the PRG loader, the Musashi oracle,
the deterministic TOS trap model and the differential driver — lives here and is bound to one
project at import time by `project.load(<recreate dir>)`.
"""
