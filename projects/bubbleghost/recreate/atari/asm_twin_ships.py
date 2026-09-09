"""Is the asm twin about to be LINKED the same transcription the differential verified?

    asm_twin_ships.py <object> <twin> <original address> <image> <load base>

prints `OK`, or one line saying how the two disagree. `build.sh` refuses the build on anything else.

WHY IT EXISTS. `../src/asm/*.S` is assembled TWICE from one source: by
`tools/recreate_kit/kit.mk` for the host differential (`-DRECREATE_HOST_DIFFERENTIAL`, the
callback-door macros), and by `build.sh` for the target (`-O2 -ffreestanding …`, the mode `-D`).
`test/test_sound_asm.py` compares the KIT's blob against the original binary's own bytes; this
compares the TARGET's object against the same reference. Together they say the two builds cannot
ship different instruction streams under one green pin — which is open in exactly the direction
kit.mk warns about, since a twin that grew an `#ifdef` would be verified in one form and shipped in
another with nothing red.

WHAT IT COMPARES. The span between `<twin>_body` and `<twin>_body_end` — the twin's own bracket
labels, which `recreate_kit/asm_twin.py` reads for the same reason — against the same many bytes of
the relocated program image at `<original address>`. The image is `gen_image.py`'s output, which IS
the original's memory at `../project.toml`'s load base, so no .PRG header arithmetic happens here.
"""
import os
import subprocess
import sys
import tempfile


def symbol_offsets(obj):
    """{name: link-time offset} for every symbol `nm` gives a value to in one object."""
    rows = (line.split() for line in
            subprocess.check_output(["m68k-elf-nm", obj], text=True).splitlines())
    return {parts[2]: int(parts[0], 16) for parts in rows if len(parts) == 3}


def flat_text(obj):
    """The object's `.text` as the bytes the linker lays down, so a symbol's value indexes it."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as flat:
        path = flat.name
    try:
        subprocess.check_call(
            ["m68k-elf-objcopy", "-O", "binary", "--only-section=.text", obj, path])
        with open(path, "rb") as binary:
            return binary.read()
    finally:
        os.unlink(path)


def compare(obj, twin, original_at, image_path, load_base):
    symbols = symbol_offsets(obj)
    start, end = f"{twin}_body", f"{twin}_body_end"
    missing = [name for name in (start, end) if name not in symbols]
    if missing:
        return f"NO BRACKET: {obj} defines no {' or '.join(missing)}, so there is no span to pin"
    mine = flat_text(obj)[symbols[start]:symbols[end]]
    if not mine:
        return f"NO BRACKET: {start} and {end} are the same address, or in the wrong order"
    with open(image_path, "rb") as image:
        theirs = image.read()[original_at - load_base:original_at - load_base + len(mine)]
    if len(mine) != len(theirs):
        return (f"MISMATCH: {twin}'s body is {len(mine)} B and the image has {len(theirs)} B left "
                f"at {original_at:#x}")
    if mine != theirs:
        differing = sum(a != b for a, b in zip(mine, theirs))
        return (f"MISMATCH: {twin}'s body differs from the original @ {original_at:#x} in "
                f"{differing} of {len(mine)} bytes")
    return "OK"


if __name__ == "__main__":
    print(compare(sys.argv[1], sys.argv[2], int(sys.argv[3], 0), sys.argv[4], int(sys.argv[5], 0)))
