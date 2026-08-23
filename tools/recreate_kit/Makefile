# The kit's own regression tests — game-agnostic checks that run standalone. Most need no
# project artifacts; the three harness-plumbing suites (`test_psg_differential.py`,
# `test_hw_differential.py`, `test_write_ledger.py`) need the SHARED liboracle.so through
# `test/kit_smoke_project.py`, so `test` builds it first (via the ORACLE_VIA delegation below) —
# without that, a fresh tree or a swept build/ dir SKIPS all three and the gate under-runs by their
# 30 cases (8 + 19 + 3, as pytest collects them). A project's `make test`
# runs its differential suite via kit.mk; this runs the kit's.
#
# The kit has no venv of its own; PY defaults to a project venv that already pins pytest.
PY ?= ../../projects/buggyboy/recreate/.venv/bin/python
# ...and it has no build of its own either: kit.mk's $(ORACLE) rule needs the KIT/GAME binding a
# project supplies. `oracle` delegates through one, so that `make -C tools/recreate_kit oracle` —
# which oracle/emu.py's stale-.so diagnostic tells every caller to run, including the standalone
# scripts that import `emu` without going through a project — is a command that exists.
ORACLE_VIA ?= ../../projects/buggyboy/recreate

.PHONY: test clean oracle
test: oracle
	$(PY) -m pytest -q test

oracle:
	$(MAKE) -C $(ORACLE_VIA) oracle

# The SHARED build artifacts: the generated Musashi opcode tables and liboracle.so, which every
# project's `make test` links against. A project's own `make clean` deliberately leaves them alone
# (deleting them would hit every other project, and race a concurrent build).
clean:
	rm -rf oracle/build
