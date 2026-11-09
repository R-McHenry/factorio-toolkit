"""native_build: build the Rust kernel and put it beside fkcore as this tree's own ``fkroute``.

    python tools/native_build.py [--debug] [--check]

``cargo build --release`` in native/fkroute, then the library copied to ``<tree>/fkroute.pyd``
(Windows; ``fkroute.so`` elsewhere). Python finds that file before any installed ``fkroute`` when
it runs from the tree (the tree is ``sys.path[0]`` for ``python -m unittest`` and ``python -m
fkcore``), so every worktree tests its own kernel and a host deploy ships the same file beside
``fkcore``. The file is gitignored. ``--check`` only reports which kernel ``import fkroute`` finds
from here, and its version. Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
CRATE = os.path.join(TREE, "native", "fkroute")


def _target():
    if sys.platform == "win32":
        return "fkroute.dll", "fkroute.pyd"
    if sys.platform == "darwin":
        return "libfkroute.dylib", "fkroute.so"
    return "libfkroute.so", "fkroute.so"


def check():
    code = ("import fkroute, sys; print(fkroute.__file__); "
            "print(getattr(fkroute, '__version__', '?'))")
    out = subprocess.run([sys.executable, "-c", code], cwd=TREE, capture_output=True, text=True)
    if out.returncode:
        print("no fkroute importable from", TREE)
        print(out.stderr.strip())
        return 1
    print(out.stdout.strip())
    return 0


def build(debug=False):
    cmd = ["cargo", "build"] + ([] if debug else ["--release"])
    print(" ".join(cmd), "in", CRATE)
    subprocess.run(cmd, cwd=CRATE, check=True)
    lib, pyd = _target()
    src = os.path.join(CRATE, "target", "debug" if debug else "release", lib)
    dst = os.path.join(TREE, pyd)
    shutil.copyfile(src, dst)
    print("->", dst, os.path.getsize(dst), "bytes")
    return check()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    return check() if a.check else build(a.debug)


if __name__ == "__main__":
    sys.exit(main())
