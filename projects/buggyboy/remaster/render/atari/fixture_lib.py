"""fixture_lib.py — shared emit helpers for the gen_*_fixture.py generators.

LOADER-ONLY by design: gen_sound_fixture.py runs at build time as a prerequisite of
libremaster.so, so anything it imports must not pull in adapter/equiv (which load recreate's .so
at import — a build-order dependency a clean `make test` can't guarantee). Keep this module free
of adapter/equiv/ctypes imports.
"""


def write_if_changed(path, text):
    """Write `text` to `path` only when the content differs, so an unchanged fixture keeps its mtime.

    The generators are re-run unconditionally by build_game.sh / bench_build.sh, so a plain write_text
    would bump the header's mtime on every build — and every make target that depends on the header
    (libremaster.so, bench.elf, the on-target build gate) would then be out of date the moment it
    finished, rebuilding on every `make test` forever. Content-stable writes make those targets truly
    incremental."""
    if not (path.exists() and path.read_text() == text):
        path.write_text(text)


def c_array(name, data):
    # aligned(2): the cores read these tables with be16/be32 (word/long moves), which fault on an odd
    # address on the 68000. A plain uint8_t[] has no alignment guarantee, so pin it to an even base.
    lines = [f"static const uint8_t {name}[{len(data)}] __attribute__((aligned(2))) = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + "".join(f"0x{b:02x}," for b in data[i:i + 16]))
    lines.append("};")
    return "\n".join(lines)


def emit_header(guard, comment, name, data):
    """Emit a self-contained generated C header as one string: a comment banner, an include guard, and a
    single c_array(name, data). `comment` is the banner's already-formatted lines (each a full '/* ...' /
    ' * ...' line). Used for every one-array fixture header so the guard/include boilerplate lives once."""
    lines = list(comment) + [
        f"#ifndef {guard}",
        f"#define {guard}",
        "#include <stdint.h>",
        "",
        c_array(name, data),
        "",
        f"#endif /* {guard} */",
        "",
    ]
    return "\n".join(lines)
