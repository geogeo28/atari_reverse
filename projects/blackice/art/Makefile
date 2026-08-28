# BLACK ICE concept art.  `make` regenerates every PNG and runs every gate.
PYTHON ?= /Users/geogeo/miniconda3/envs/atari_reverse/bin/python

.PHONY: all clean check ledger

all:
	$(PYTHON) build_art.py

check:
	$(PYTHON) palette.py
	$(PYTHON) textures.py
	$(PYTHON) sprites.py
	$(PYTHON) rimtest.py

ledger:
	$(PYTHON) -c "import build_art; build_art.print_ledger()"

clean:
	rm -rf out
