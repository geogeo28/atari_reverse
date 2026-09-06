"""The image a differential STARTS from, and the one sanctioned way to change it.

`harness.make_image()` copies `harness.BASE_IMAGE` — the project's .PRG loaded and relocated — and
every `differential()` is built on that copy. For most games that is the machine their functions are
entered on. For a game whose startup writes its own state before `main` runs it is not: Bubble
Ghost's crt0 ends by calling `init_globals`, which fills a bss the loaded image holds as ZEROES, so
a case staged on BASE_IMAGE runs against a program whose tables are all zero and goes green about a
machine that never exists at run time.

`harness.set_base_image()` is the way in, and this pins the three things a project rests on it for:
that a differential really runs on what was installed (not merely that a variable changed), that a
wrong-sized image is refused by name rather than quietly truncating the map, and that the previous
image comes back so a session fixture can restore it.

The module skips whole when the shared oracle or a C compiler is absent — `oracle/build/` is
gitignored, so a bare checkout is a normal state to be in (`test_entry_state.py`'s convention).
"""
import pytest

from kit_smoke_project import HEAP_RESULT, bind

harness = bind()

RTS = b"\x4e\x75"
NO_OP_GLUE = lambda lib, buf: None   # noqa: E731 — nothing is compared but the memory

# Where the installed image differs from the loaded one: in-image, above the miniature project's
# program and below OS_FS_TABLE, so writing code there disturbs nothing else the suite stages.
PATCH_AT = HEAP_RESULT


@pytest.fixture
def installed_base():
    """Install a base image carrying an `rts` at PATCH_AT, and put the loaded one back after."""
    patched = bytearray(harness.BASE_IMAGE)
    patched[PATCH_AT:PATCH_AT + len(RTS)] = RTS
    previous = harness.set_base_image(patched)
    try:
        yield bytes(patched)
    finally:
        harness.set_base_image(previous)


def test_make_image_starts_from_the_installed_image(installed_base):
    assert bytes(harness.make_image()[PATCH_AT:PATCH_AT + len(RTS)]) == RTS


def test_a_differential_really_runs_on_the_installed_image(installed_base):
    """The pin that matters: the ORACLE executed an instruction that exists only in what was set.

    Asserting the module variable moved would prove nothing about a `differential()` that had
    captured the old image at import — and PATCH_AT holds zeroes in the loaded image, which is not
    an `rts` at all, so a run that started from BASE_IMAGE could not return from here.
    """
    diffs, _info = harness.differential(PATCH_AT, {}, NO_OP_GLUE)
    assert diffs == []


def test_the_loaded_image_is_what_a_project_gets_by_default():
    """The control, and the restore: outside the fixture the base is the .PRG as loaded."""
    assert bytes(harness.make_image()[PATCH_AT:PATCH_AT + len(RTS)]) != RTS
    assert bytes(harness.make_image()) == bytes(harness.BASE_IMAGE)


def test_set_base_image_hands_back_the_previous_one(installed_base):
    """A fixture restores by installing what it was given back, so that value must be the old image."""
    previous = harness.set_base_image(installed_base)
    assert bytes(previous) == installed_base
    assert bytes(harness.set_base_image(previous)) == installed_base


@pytest.mark.parametrize("length", (harness.OS_IMAGE_SIZE - 1, harness.OS_IMAGE_SIZE + 1, 0))
def test_an_image_of_the_wrong_length_is_refused_by_name(length):
    """Every address the model fixes is an offset into an image of exactly OS_IMAGE_SIZE bytes."""
    with pytest.raises(ValueError) as excinfo:
        harness.set_base_image(bytes(length))
    message = str(excinfo.value)
    assert "OS_IMAGE_SIZE" in message and f"{harness.OS_IMAGE_SIZE:#x}" in message


def test_the_installed_image_is_a_copy_the_caller_cannot_mutate():
    """It is shared by every case in a session, so a bytearray the caller kept must not reach it."""
    mutable = bytearray(harness.BASE_IMAGE)
    previous = harness.set_base_image(mutable)
    try:
        mutable[PATCH_AT] ^= 0xFF
        assert harness.make_image()[PATCH_AT] != mutable[PATCH_AT]
    finally:
        harness.set_base_image(previous)
