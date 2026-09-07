"""Command-line interface: ``python -m cimbar encode|decode``."""

import argparse
import glob
import os
import sys

from . import encode as encode_bytes, Decoder
from .protocol import _parse_container  # noqa: F401 (kept for potential reuse)


def _expand(paths):
    out = []
    for p in paths:
        hits = glob.glob(p)
        out.extend(sorted(hits) if hits else [p])
    return out


def cmd_encode(args):
    with open(args.input, "rb") as f:
        data = f.read()
    name = os.path.basename(args.input)
    frames = encode_bytes(data, name)

    prefix = args.output or (os.path.splitext(name)[0] + "_cimbar")
    saved = []
    if not args.gif_only:
        outdir = os.path.dirname(prefix)
        if outdir and not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        for i, im in enumerate(frames):
            path = "%s_%04d.png" % (prefix, i)
            im.save(path)
            saved.append(path)

    if args.gif:
        frames[0].save(
            args.gif, save_all=True, append_images=frames[1:],
            duration=int(1000 / max(1, args.fps)), loop=0,
        )

    print("Encoded %d bytes (%s) into %d frame(s)." % (len(data), name, len(frames)))
    if saved:
        print("  frames: %s ... %s" % (saved[0], saved[-1]) if len(saved) > 1 else "  frame: %s" % saved[0])
    if args.gif:
        print("  gif:    %s (%d fps)" % (args.gif, args.fps))
    return 0


def cmd_decode(args):
    files = _expand(args.frames)
    if not files:
        print("no frame images given", file=sys.stderr)
        return 2

    dec = Decoder()
    for path in files:
        try:
            done = dec.add(path)
        except Exception as exc:  # noqa: BLE001
            print("  ! %s: %s" % (path, exc), file=sys.stderr)
            continue
        if done:
            break

    if not dec.complete():
        print("Incomplete: read %d frame(s), still missing %r"
              % (dec.frames_read, dec.missing()), file=sys.stderr)
        return 1

    name, data = dec.result()
    outdir = args.output or "."
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, os.path.basename(name) or "cimbar_output.bin")
    with open(outpath, "wb") as f:
        f.write(data)
    print("Decoded %d bytes -> %s (%d frames read, %d failed)"
          % (len(data), outpath, dec.frames_read, dec.frames_failed))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="cimbar", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode", help="encode a file into cimbar frames")
    e.add_argument("-i", "--input", required=True, help="input file")
    e.add_argument("-o", "--output", help="output prefix (default: <name>_cimbar)")
    e.add_argument("--gif", help="also write an animated GIF to this path")
    e.add_argument("--gif-only", action="store_true", help="write only the GIF, no PNGs")
    e.add_argument("--fps", type=int, default=15, help="GIF frame rate (default 15)")
    e.set_defaults(func=cmd_encode)

    d = sub.add_parser("decode", help="decode cimbar frames back into a file")
    d.add_argument("frames", nargs="+", help="frame image paths or globs")
    d.add_argument("-o", "--output", help="output directory (default: .)")
    d.set_defaults(func=cmd_decode)

    g = sub.add_parser("gui", help="launch the drag-and-drop desktop app")
    g.set_defaults(func=cmd_gui)
    return p


def cmd_gui(args):
    from .gui import main as gui_main
    return gui_main()


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
