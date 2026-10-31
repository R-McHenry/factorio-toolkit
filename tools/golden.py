"""golden: the 2.1 golden check (PLAN-2.1, "The golden check"). Stdlib only.

    python tools/golden.py snapshot --tree PATH --out DIR [--jobs N] [--only SUBSTR]
    python tools/golden.py compare DIR_A DIR_B [--lines N]

``snapshot`` runs PATH's own fkcore (a subprocess per corpus file, cwd = the file's folder,
PYTHONPATH = PATH) on every file of the corpus and writes, per file, ``DIR/<corpus path>.txt``:

- ``elaborate``: the netlist as ``fk check`` / ``fk rates`` see it (``_flat``: elaborated, n=auto
  sized): every machine, net (items, drivers, consumers), sealed port, lane pair and check line;
- ``rates``: what ``python -m fkcore rates FILE`` prints (stdout, stderr and its exit code);
- ``layout``: the ``.fkp`` placements ``fk layout`` would write (``expand_factory`` over the
  committed ``.fkp``, as text, never saved), and the invariants it breaks.

An error is output too: the step's message and exit code (an exception's type and message, not its
traceback, so a moved line in fkcore is not a difference). Paths are written relative to the
corpus root (``<ROOT>``), so trees at different places snapshot alike; the version string is
``<VERSION>``. ``DIR/_meta.txt`` holds the version, commit, corpus size and run time (not compared).

The corpus: every ``.fk`` under ``agent/docs/examples``, ``games``, ``tests/data`` and
``kickoff/template`` of PATH, plus the frozen designs under ``tests/golden/<name>/`` of the tree
this script is in (``--frozen`` to change), so the corpus is the same whichever tree is checked.
A frozen folder's ``ENTRY`` file names its entry points (default: every ``.fk`` in it).

``compare`` prints identical / different per file, with a short unified diff, and exits 1 on any
difference (0 when all are identical).
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = ("agent/docs/examples", "games", "tests/data", "kickoff/template")
FROZEN = os.path.join(os.path.dirname(HERE), "tests", "golden")
META = "_meta.txt"

# -- the driver: runs inside the checked tree's interpreter, one corpus file per process ----------
DRIVER = r'''
import contextlib, dataclasses, io, os, re, sys, traceback
FILE, ROOT = sys.argv[1], sys.argv[2]
out = []

def fmt(v):
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return type(v).__name__ + "(" + ", ".join(
            f"{f.name}={fmt(getattr(v, f.name, None))}" for f in dataclasses.fields(v)) + ")"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{fmt(k)}: {fmt(x)}" for k, x in
                               sorted(v.items(), key=lambda kv: repr(kv[0]))) + "}"
    if isinstance(v, (set, frozenset)):
        return "{" + ", ".join(sorted(fmt(x) for x in v)) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    if isinstance(v, tuple):
        return "(" + ", ".join(fmt(x) for x in v) + ")"
    if isinstance(v, float):
        return repr(v)
    return re.sub(r" at 0x[0-9a-fA-F]+", "", repr(v))

def run(fn):
    """fn() with stdout/stderr captured -> (result, stdout, stderr, status)."""
    so, se = io.StringIO(), io.StringIO()
    res, status = None, "ok"
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            res = fn()
            if isinstance(res, int) and not isinstance(res, bool):
                status = f"exit {res}"
        except SystemExit as exc:
            status = f"exit {exc.code}"
        except Exception as exc:
            msg = str(exc).splitlines()
            status = f"exception {type(exc).__name__}: " + " | ".join(m.rstrip() for m in msg)
    return res, so.getvalue(), se.getvalue(), status

def block(title, text):
    if text.strip():
        out.append(f"-- {title}")
        out.extend(text.rstrip("\n").split("\n"))

def attr(o, name, default=None):
    return getattr(o, name, default)

import fkcore
from fkcore import __main__ as fkmain
from fkcore import fkp
from fkcore.catalog import Catalog

out.append(f"== golden {FILE}")
flat, so, se, status = run(lambda: fkmain._flat(FILE))
out.append("== elaborate")
out.append(f"status {status if flat is None else 'ok'}")
block("stdout", so)
block("stderr", se)
if flat is not None:
    out.append(f"name {flat.name}")
    sizing = attr(flat, "_sizing")
    if sizing is not None:
        out.append(f"sized {fmt(sizing[1])}")
    ms = attr(flat, "machines", {})
    out.append(f"machines {len(ms)}")
    for k in sorted(ms):
        m = ms[k]
        out.append("m " + k + " " + " ".join(f"{f}={fmt(attr(m, f))}" for f in (
            "inst", "kind", "prototype", "recipe", "needs", "makes", "takes", "sink", "drain",
            "source", "duty", "extra")))
    ns = attr(flat, "nets", {})
    out.append(f"nets {len(ns)}")
    for k in sorted(ns):
        n = ns[k]
        out.append("n " + k + " " + " ".join(
            [f"items={fmt(list(n.items))}",
             f"drivers={fmt(sorted(n.drivers, key=repr))}",
             f"consumers={fmt(sorted(n.consumers, key=repr))}"]
            + [f"{f}={fmt(attr(n, f))}" for f in ("declared", "limited", "width", "lane", "scope")]
            + [f"when={attr(n, 'when')[0] if attr(n, 'when') else None}"]))
    ps = attr(flat, "ports", {})
    out.append(f"ports {len(ps)}")
    for k in sorted(ps):
        p = ps[k]
        out.append("p " + k + " " + " ".join(f"{f}={fmt(attr(p, f))}" for f in (
            "dir", "items", "right", "lane", "side", "pos", "scope", "module", "size")))
    pt = attr(flat, "port_tiles", {})
    for k in sorted(pt):
        out.append(f"pt {k} {fmt(pt[k])}")
    out.append(f"sealed {fmt(attr(flat, 'sealed', set()))}")
    out.append(f"dnp {fmt(attr(flat, 'dnp', set()))}")
    pairs = attr(flat, "pairs", {})
    for k in sorted(pairs):
        out.append(f"pair {k} {fmt(pairs[k])}")
    st = attr(flat, "stacks", {})
    for k in sorted(st):
        out.append(f"stack {k} {fmt(st[k])}")
    ch = attr(flat, "choices", {})
    for k in sorted(ch):
        out.append(f"choice {k} {fmt(ch[k])}")
    checks = [str(c) for c in attr(flat, "checks", [])]
    out.append(f"checks {len(checks)}")
    out.extend("c " + c for c in checks)

out.append("== rates")
_r, so, se, status = run(lambda: fkmain.main(["rates", FILE]))
out.append(f"status {status}")
block("stdout", so)
block("stderr", se)

out.append("== layout")
if flat is None:
    out.append("status no netlist")
else:
    def layout():
        from fkcore import expand
        cat = Catalog.load()
        p = os.path.splitext(FILE)[0] + ".fkp"
        previous = fkp.load(p) if os.path.exists(p) else None
        lay, notes = expand.expand_factory(flat, cat, previous)
        return lay, notes, fkp.invariants(lay, cat)
    res, so, se, status = run(layout)
    out.append(f"status {status}")
    block("stdout", so)
    block("stderr", se)
    if res is not None:
        lay, notes, problems = res
        out.extend("note " + str(n) for n in notes)
        out.append(f"invariants {len(problems)}")
        out.extend("inv " + str(p) for p in problems)
        out.extend(fkp.dumps(lay).rstrip("\n").split("\n"))

text = "\n".join(out) + "\n"
ver = getattr(fkcore, "__version__", "")
if ver:
    text = text.replace(ver, "<VERSION>")
for r in sorted({ROOT, os.path.abspath(ROOT), os.path.realpath(ROOT)}, key=len, reverse=True):
    for form in {r, r.replace("\\", "/"), r.replace("/", "\\")}:
        text = re.sub(re.escape(form), "<ROOT>", text, flags=re.IGNORECASE)
text = re.sub(r"<ROOT>[^\s'\"(),;]*", lambda m: m.group(0).replace("\\", "/"), text)
sys.stdout.buffer.write(text.encode("utf-8"))
'''


def corpus(tree, frozen=FROZEN):
    """-> [(corpus path, root, path relative to root)], sorted. Frozen designs are ``tests/golden/
    <name>/...`` under their own root (the folder that holds ``tests``)."""
    files = []
    for src in SOURCES:
        base = os.path.join(tree, *src.split("/"))
        for dirpath, dirnames, names in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in ("out", "__pycache__"))
            for n in names:
                if n.endswith(".fk"):
                    rel = os.path.relpath(os.path.join(dirpath, n), tree).replace("\\", "/")
                    files.append((rel, tree, rel))
    if frozen and os.path.isdir(frozen):
        froot = os.path.dirname(os.path.dirname(os.path.abspath(frozen)))
        for name in sorted(os.listdir(frozen)):
            d = os.path.join(frozen, name)
            if not os.path.isdir(d):
                continue
            entry = os.path.join(d, "ENTRY")
            if os.path.exists(entry):
                with open(entry, encoding="utf-8") as fh:
                    picks = [ln.split("#")[0].strip() for ln in fh]
                picks = [p for p in picks if p]
            else:
                picks = sorted(n for n in os.listdir(d) if n.endswith(".fk"))
            for n in picks:
                rel = os.path.relpath(os.path.join(d, n), froot).replace("\\", "/")
                files.append((rel, froot, rel))
    return sorted(files)


def _env(tree, hashseed="0"):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k != "FK_LINK"}
    env.update(PYTHONPATH=os.path.abspath(tree), PYTHONIOENCODING="utf-8", PYTHONHASHSEED=hashseed,
               PYTHONUTF8="1",
               # bytecode goes to a cache of our own, never into the checked tree
               PYTHONPYCACHEPREFIX=os.path.join(tempfile.gettempdir(), "fk-golden-pycache"))
    return env


def _one(tree, item, env, timeout):
    rel, root, _ = item
    path = os.path.join(root, *rel.split("/"))
    cmd = [sys.executable, "-c", DRIVER, os.path.basename(path), root]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=os.path.dirname(path), env=env, capture_output=True,
                           timeout=timeout)
        text = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0:
            err = p.stderr.decode("utf-8", "replace").strip().splitlines()
            text += f"== driver failed: exit {p.returncode}: {err[-1] if err else ''}\n"
    except subprocess.TimeoutExpired:
        text = f"== golden {os.path.basename(path)}\n== driver timed out after {timeout} s\n"
    return rel, text, time.time() - t0


def _git(tree, *args):
    try:
        return subprocess.run(["git", "-C", tree, *args], capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _tree_version(tree, env):
    p = subprocess.run([sys.executable, "-c", "import fkcore; print(fkcore.__version__)"],
                       cwd=tree, env=env, capture_output=True, text=True, timeout=60)
    return p.stdout.strip() or "?"


def snapshot(tree, out, jobs=0, only="", frozen=FROZEN, timeout=900, quiet=False, hashseed="0"):
    """Snapshot TREE's corpus into OUT. -> (number of files, seconds)."""
    tree = os.path.abspath(tree)
    if not os.path.isdir(os.path.join(tree, "fkcore")):
        raise SystemExit(f"error: {tree} has no fkcore")
    items = [it for it in corpus(tree, frozen) if only in it[0]]
    env = _env(tree, hashseed)
    t0 = time.time()
    jobs = jobs or min(len(items), os.cpu_count() or 4) or 1
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda it: _one(tree, it, env, timeout), items))
    took = time.time() - t0
    os.makedirs(out, exist_ok=True)
    for rel, text, _sec in results:
        dest = os.path.join(out, *(rel + ".txt").split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    slow = sorted(results, key=lambda r: -r[2])[:3]
    meta = [f"tree {tree}", f"version {_tree_version(tree, env)}",
            f"commit {_git(tree, 'rev-parse', 'HEAD') or '?'}",
            f"dirty {'yes' if _git(tree, 'status', '--porcelain', '--', 'fkcore') else 'no'}",
            f"files {len(results)}", f"jobs {jobs}", f"seconds {took:.1f}",
            "slowest " + ", ".join(f"{r} {s:.1f}s" for r, _t, s in slow)]
    with open(os.path.join(out, META), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(meta) + "\n")
    if not quiet:
        errs = sum(1 for _r, t, _s in results if "status exit 2" in t or "status exception" in t
                   or "== driver" in t)
        print(f"golden snapshot: {len(results)} files from {tree} in {took:.1f} s "
              f"({jobs} jobs; {errs} with an error, kept as output) -> {out}")
    return len(results), took


def _files(d):
    got = {}
    for dirpath, _dirs, names in os.walk(d):
        for n in names:
            if n.endswith(".txt") and n != META:
                p = os.path.join(dirpath, n)
                got[os.path.relpath(p, d).replace("\\", "/")[:-4]] = p
    return got


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _meta(d):
    try:
        return dict(ln.split(" ", 1) for ln in _read(os.path.join(d, META)).splitlines()
                    if " " in ln)
    except OSError:
        return {}


def compare(a, b, lines=30, out=None):
    """Print per-file identical/different. -> the number of files that differ."""
    out = out or sys.stdout
    fa, fb = _files(a), _files(b)
    ma, mb = _meta(a), _meta(b)
    print(f"A {a} (version {ma.get('version', '?')}, {ma.get('commit', '?')[:10]})", file=out)
    print(f"B {b} (version {mb.get('version', '?')}, {mb.get('commit', '?')[:10]})", file=out)
    bad = 0
    for rel in sorted(set(fa) | set(fb)):
        if rel not in fb or rel not in fa:
            bad += 1
            print(f"only in {'A' if rel in fa else 'B'}  {rel}", file=out)
            continue
        ta, tb = _read(fa[rel]), _read(fb[rel])
        for m in (ma, mb):          # the version string, masked (snapshots mask it already)
            v = m.get("version", "")
            if v and v != "?":
                ta, tb = ta.replace(v, "<VERSION>"), tb.replace(v, "<VERSION>")
        if ta == tb:
            print(f"identical  {rel}", file=out)
            continue
        bad += 1
        print(f"different  {rel}", file=out)
        diff = list(difflib.unified_diff(ta.splitlines(), tb.splitlines(), "A/" + rel,
                                         "B/" + rel, n=1, lineterm=""))
        for ln in diff[:lines]:
            print("    " + ln, file=out)
        if len(diff) > lines:
            print(f"    ... {len(diff) - lines} more diff lines", file=out)
    n = len(set(fa) | set(fb))
    print(f"golden compare: {n - bad} of {n} identical, {bad} different", file=out)
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(prog="golden", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="run TREE's fkcore on the corpus and write DIR")
    s.add_argument("--tree", required=True, help="a v5 tree (the one whose fkcore runs)")
    s.add_argument("--out", required=True, help="where the snapshot goes (made if missing)")
    s.add_argument("--jobs", type=int, default=0, help="processes at once (default: CPUs)")
    s.add_argument("--only", default="", help="only corpus paths containing this text")
    s.add_argument("--frozen", default=FROZEN, help="the frozen designs (default: this tree's "
                   "tests/golden; '' for none)")
    s.add_argument("--timeout", type=int, default=900, help="seconds per file")
    s.add_argument("--hashseed", default="0", help="PYTHONHASHSEED for the runs (default 0; "
                   "'random' shows whether the output hangs on set order)")
    c = sub.add_parser("compare", help="compare two snapshots; exit 1 on any difference")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--lines", type=int, default=30, help="diff lines shown per file")
    sub.add_parser("list", help="the corpus of a tree").add_argument("--tree", default=".")
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        snapshot(a.tree, a.out, a.jobs, a.only, a.frozen or None, a.timeout, hashseed=a.hashseed)
        return 0
    if a.cmd == "list":
        items = corpus(os.path.abspath(a.tree))
        for rel, _root, _ in items:
            print(rel)
        print(f"{len(items)} files")
        return 0
    return 1 if compare(a.a, a.b, a.lines) else 0


if __name__ == "__main__":
    sys.exit(main())
