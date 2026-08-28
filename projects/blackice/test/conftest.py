import ctypes
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import blackice


@pytest.fixture(scope="session")
def lib():
    return blackice.load()


@pytest.fixture(scope="session")
def level1(lib):
    path = blackice.ROOT / "levels" / "level1.txt"
    return blackice.parse_level(lib, path.read_text())
