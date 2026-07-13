# Build the reconstruction (candidate) and the Musashi-backed oracle, then run the
# differential harness. `make test` rebuilds both libs and runs pytest.
CC      ?= clang
CFLAGS  ?= -std=c11 -O2 -fPIC -Wall -Wextra -Iinclude
PY      := .venv/bin/python

CAND    := build/libbuggyboy.so
SRC     := $(wildcard src/*.c)

MUSASHI := oracle/musashi
GENDIR  := oracle/build
ORACLE  := oracle/build/liboracle.so
OCFLAGS := -O2 -fPIC -Iinclude -I$(MUSASHI) -I$(GENDIR) -I$(MUSASHI)/softfloat

$(CAND): $(SRC) $(wildcard include/*.h)
	@mkdir -p build
	$(CC) $(CFLAGS) -shared $(SRC) -o $(CAND)

# Musashi generates its opcode tables from m68k_in.c before the core can compile.
$(MUSASHI)/m68kcpu.c:
	git clone --depth 1 https://github.com/kstenerud/Musashi.git $(MUSASHI)

$(GENDIR)/m68kops.c: $(MUSASHI)/m68kmake.c $(MUSASHI)/m68k_in.c
	@mkdir -p $(GENDIR)
	$(CC) -O2 -o $(GENDIR)/m68kmake $(MUSASHI)/m68kmake.c
	cd $(GENDIR) && ./m68kmake . ../musashi/m68k_in.c

$(ORACLE): oracle/shim.c include/os.h $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c
	$(CC) $(OCFLAGS) -shared \
	  $(MUSASHI)/m68kcpu.c $(GENDIR)/m68kops.c $(MUSASHI)/softfloat/softfloat.c oracle/shim.c \
	  -o $(ORACLE)

.PHONY: test clean venv
# Create the project venv and install the pinned Python deps (numpy, pyresidfp, pytest).
venv:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt

test: $(CAND) $(ORACLE)
	$(PY) -m pytest -q test

clean:
	rm -rf build $(GENDIR)/m68kmake $(GENDIR)/m68kops.* $(ORACLE)