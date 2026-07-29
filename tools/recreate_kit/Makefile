# The kit's own regression tests — game-agnostic checks that need no project (no oracle build,
# no candidate .so), so they run standalone. A project's `make test` runs its differential suite
# via kit.mk; this runs the kit's.
#
# The kit has no venv of its own; PY defaults to a project venv that already pins pytest.
PY ?= ../../projects/buggyboy/recreate/.venv/bin/python

.PHONY: test clean
test:
	$(PY) -m pytest -q test

# The SHARED build artifacts: the generated Musashi opcode tables and liboracle.so, which every
# project's `make test` links against. A project's own `make clean` deliberately leaves them alone
# (deleting them would hit every other project, and race a concurrent build).
clean:
	rm -rf oracle/build
