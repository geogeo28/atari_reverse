#!/usr/bin/env python3
"""What every static depacker in this workspace shares: its command line and its size cap.

`depack_lsd.py` and `depack_rad.py` each know exactly one container and deliberately do not
import each other. Everything AROUND the decode is identical, though — parse the arguments,
read the file, write the output, pick an exit status — so it lives here once instead of being
copied per tool, where a fix would have to be made twice. Stdlib only, like the depackers.

    import depack_common                         # tools/ is on sys.path beside this file

    if __name__ == "__main__":
        sys.exit(depack_common.main("depack_x.py", __doc__, _decode, DepackError))

Exit status, the same for every depacker:
  0  depacked
  1  unreadable input, unwritable output, or not a stream that depacker handles
  2  bad command line
"""
import sys

OUT_FLAG = "-o"
DEFAULT_OUT_SUFFIX = ".out"
# Refuse a claimed unpacked size that cannot describe a real ST buffer, BEFORE allocating it: a
# corrupt or misidentified header (be32 0xffffffff) would otherwise ask for a 4 GB bytearray. The
# 68000 addresses 16 MB total, so nothing any of these routines ever wrote can be larger.
MAX_UNPACKED = 16 << 20


def _usage(tool):
    return "usage: %s PACKED [-o OUT]" % tool


def _parse_args(tool, args):
    """(packed path, output path) — or (None, None) after printing why the command line is unusable."""
    if args[0].startswith("-"):
        sys.stderr.write("%s\n" % _usage(tool))
        return None, None
    src = args[0]
    dst = src + DEFAULT_OUT_SUFFIX
    if OUT_FLAG in args:
        flag = args.index(OUT_FLAG)
        if flag + 1 >= len(args):
            sys.stderr.write("%s needs an output file\n%s\n" % (OUT_FLAG, _usage(tool)))
            return None, None
        dst = args[flag + 1]
    return src, dst


def main(tool, doc, decode, error):
    """Run one depacker's command line; return its exit status.

    `tool` names the script in its messages, `doc` is that depacker's module docstring (what
    `--help` prints), `decode(data) -> bytes` inflates a whole file, and `error` is the exception
    `decode` raises for a file that depacker does not handle.
    """
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(doc.strip())
        return 0
    src, dst = _parse_args(tool, args)
    if src is None:
        return 2
    try:
        with open(src, "rb") as fh:
            data = fh.read()
    except OSError as err:
        sys.stderr.write("cannot read %s: %s\n" % (src, err))
        return 1
    try:
        out = decode(data)
    except error as err:
        sys.stderr.write("%s: %s\n" % (src, err))
        return 1
    try:
        with open(dst, "wb") as fh:
            fh.write(out)
    except OSError as err:
        sys.stderr.write("cannot write %s: %s\n" % (dst, err))
        return 1
    print("depacked %s -> %s" % (src, dst))
    print("  %d packed -> %d bytes  |  first 16: %s" % (len(data), len(out), out[:16].hex()))
    return 0
