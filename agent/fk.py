"""fk: the agent's one command, on the laptop. The game host is an implementation detail.

A run folder holds ``game\\`` (the game codebase the agent edits: ``.fk`` modules, the surface file,
the build script), ``bin\\`` (this file and ``fk.cmd``), ``.toolkit\\`` (the toolkit, pinned for the
run) and ``run.json``, which names the game host, the host's copy of the run and the host's
toolkit (also pinned: files a running session uses never change under it). Each command:

1. runs where it belongs. Design and every pure command run here, where the CPU is (elaborate,
   rates, plan, place, route, cover, floorplan, checks, write_layout). Whatever reads or writes
   the game runs on the host, where RCON is: diff, apply, a live look, a wait, measure, alerts,
   stats, chart, terrain, chat.
2. keeps the two copies of ``game\\`` in step: what changed here is pushed before a host step, and
   what the host wrote is pulled after it. Changed means content (``out\\.synced`` keeps each
   file's hash at the last sync), a pull keeps a file edited here since (the next push sends
   it), and the syncs of two fk commands take turns (1.4.2: a player's background ``fk look``
   loop pulled the host's copy over fresh edits, which the next push then skipped by mtime).
3. ends with the footer, ``fkcore poll``: chat lines that are new since the last command, and the
   game's new alerts and reminders.

``fk build`` splits the flow at its first game step: design here, then on the host the steps from
``diff`` on (``--from diff``: the floorplan is replayed on the checkpoints). One build at a time
in a run (2.0: a lead player's workers may build at once, and two builds would paste over each
other's design): a second ``fk build`` waits for the first. Stdlib only. ``FK_RUN`` names the run
folder (default: the folder above this file's).

``fk lua`` sends its chunk (the argument, or ``--file F``'s text) over the ssh's stdin, never on
the command line (1.2): Git for Windows' ssh, an MSYS program, gets at most about 8 kB of one
argument, so a 13 kB chunk arrived cut, and its open single quote stopped the host's shell.

``fk stage`` (2.0) is the staged plan, all of it here: its repository is ``<run>\\.stage`` (game\\
is its work tree, so no sync carries it) and its stage folders ``<run>\\stages\\N``.

``fk lab NAME`` (2.0.3) builds a factory on its own slot of the lab surface and ``fk lab NAME
--measure S`` measures it there (``fkcore.lab``), on the host; ``--from DIR`` (a stage folder, a
scratch copy) sends that folder to the host's copy of the run first, beside game\\.

A run whose ``run.json`` says ``"host": "local"`` plays a game on this machine (a laptop test
server, ``tools/laptop_server.py``): nothing is copied, and the game steps run here with the
link settings in ``run.json``'s ``env`` (FK_RCON_PORT, FK_RCON_PW_FILE, FK_SCRIPT_OUTPUT).
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import tarfile
import time

RUN = os.path.abspath(os.environ.get("FK_RUN") or os.path.join(os.path.dirname(__file__), ".."))
GAME = os.path.join(RUN, "game")
STAMP = os.path.join(GAME, "out", ".synced")

#: commands that are pure: they run here, on the run's own toolkit
LOCAL = {"rates", "plan", "check", "explain", "unfold", "render", "layout", "split-to-chest",
         "merge", "insert", "chests-to-net", "net-to-chests"}
#: commands that need the game: they run on the host, with the link on
HOST = {"chat", "say", "poll", "ack", "alerts", "stats", "chart", "stock", "read-terrain", "measure",
        "adopt", "sense", "research", "tech", "recipes", "lua", "fresh", "avail"}
#: host commands whose first word may be the area, as for look: ``fk fresh X0,Y0,X1,Y1``
AREA_FIRST = ("fresh", "measure")
#: files only the host writes: pulled, never pushed
HOST_MADE = ("out/.synced", "out/chat-cursor.json", "out/chat-ack.json", "out/alerts.json",
             "out/inbox.txt")
#: the build steps that read or write the game
LINK_STEPS = ("diff", "apply")


def _config():
    with open(os.path.join(RUN, "run.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("host", "computah-ct")
    return cfg


def _ssh(cfg, command, data=None, capture=False):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", cfg["host"], command], input=data,
                          stdout=subprocess.PIPE if capture else None)


def _host_made(rel):
    return any(rel == h or rel.startswith(h.rstrip("/") + "/") for h in HOST_MADE)


def _sync_file(rel):
    """The sync's own files (the manifest, its lock): never sent, never taken."""
    return rel == "out/.synced" or rel.startswith("out/.synced.")


def _sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _synced():
    """{file: sha1} as the last sync left game\\, or None: no sync yet, or an older fk's plain
    stamp (that push goes by mtime once, then by content)."""
    try:
        with open(STAMP, encoding="utf-8") as fh:
            files = json.load(fh)["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return files if isinstance(files, dict) else None


def _save_synced(cfg, files):
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    tmp = f"{STAMP}.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"with": f"{cfg['host']}:{cfg['host_game']}", "at": time.ctime(),
                   "files": files}, fh)
    os.replace(tmp, STAMP)


@contextlib.contextmanager
def _turn():
    """One sync at a time in a run: a second fk (a background loop of the player's) waits here,
    so its pull never lands between another command's edit and that edit's push."""
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    with open(STAMP + ".lock", "a+b") as fh:
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:                # LK_LOCK gives up after 10 s: wait on
                    pass
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


@contextlib.contextmanager
def _build_lock():
    """One ``fk build`` at a time in a run: a second one waits here, and says so once. The lock
    file is in the run folder, outside game\\, so no sync carries it."""
    with open(os.path.join(RUN, ".fk-build.lock"), "a+b") as fh:
        said = False
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if not said:
                        print("fk build: another build runs in this run; this one waits for it",
                              flush=True)
                        said = True
                    time.sleep(2)
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                print("fk build: another build runs in this run; this one waits for it", flush=True)
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


def push(cfg):
    """Send the files of game\\ whose content changed here since the last sync (host-made files
    excepted)."""
    if cfg["host"] == "local":
        return 0
    with _turn():
        synced = _synced()
        since = os.path.getmtime(STAMP) if synced is None and os.path.exists(STAMP) else 0
        now, buf, n = {}, io.BytesIO(), 0
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for root, _dirs, files in os.walk(GAME):
                for name in files:
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, GAME).replace("\\", "/")
                    if _host_made(rel) or _sync_file(rel):
                        continue
                    now[rel] = sha = _sha(full)
                    if (synced.get(rel) != sha if synced is not None
                            else os.path.getmtime(full) > since):
                        tar.add(full, arcname=rel)
                        n += 1
        if n:
            r = _ssh(cfg, f"mkdir -p {shlex.quote(cfg['host_game'])} && "
                          f"tar -xf - -C {shlex.quote(cfg['host_game'])}", data=buf.getvalue())
            if r.returncode:
                sys.exit(f"fk: push to {cfg['host']} failed")
        _save_synced(cfg, {**(synced or {}), **now})
    return n


def pull(cfg):
    """Bring what the host wrote in its copy of game\\ back here. A file whose content changed
    here since the last sync keeps the change (the next push sends it)."""
    if cfg["host"] == "local":
        return
    with _turn():
        r = _ssh(cfg, f"tar -cf - -C {shlex.quote(cfg['host_game'])} .", capture=True)
        if r.returncode:
            sys.exit(f"fk: pull from {cfg['host']} failed")
        synced = _synced()
        files, take = dict(synced or {}), []
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
            for m in tar.getmembers():
                if not (m.isfile() or m.isdir()) or m.name.startswith("/") \
                        or ".." in m.name.split("/"):
                    continue
                rel = m.name
                while rel.startswith("./"):
                    rel = rel[2:]
                full = os.path.join(GAME, rel)
                if m.isfile() and (_sync_file(rel) or (
                        synced is not None and not _host_made(rel) and os.path.isfile(full)
                        and _sha(full) != synced.get(rel))):
                    continue                   # the sync's own, or edited here since the sync
                take.append((m, rel))
            tar.extractall(GAME, members=[m for m, _rel in take], filter="data")
        for m, rel in take:
            if m.isfile():
                files[rel] = _sha(os.path.join(GAME, rel))
        _save_synced(cfg, files)


def local(cfg, args):
    env = dict(os.environ, PYTHONPATH=os.path.join(RUN, ".toolkit"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("FK_LINK", None)
    return subprocess.run([sys.executable, "-m", "fkcore"] + args, cwd=GAME, env=env).returncode


#: what the design half reads about the game: the host writes it, the laptop only reads it
AVAIL = os.path.join(GAME, "out", "avail.json")


def _avail_first(cfg):
    """One host read of what ``inserter=any`` / ``--hand any`` / ``--pole any`` can build, before a
    design half that has no snapshot yet (the first build of a run): without it the first build
    chooses blind, which is how a run used to paste inserters its network could not build."""
    if cfg["host"] == "local" or os.path.exists(AVAIL):
        return
    remote(cfg, ["avail", ".", "--save"], footer=False)
    pull(cfg)


def remote(cfg, args, footer=True, data=None):
    """``fkcore ARGS`` on the host (``data``: bytes for its stdin)."""
    if cfg["host"] == "local":
        env = dict(os.environ, PYTHONPATH=os.path.join(RUN, ".toolkit"), FK_LINK="on",
                   PYTHONDONTWRITEBYTECODE="1", **{k: v for k, v in cfg.get("env", {}).items() if v})
        code = subprocess.run([sys.executable, "-m", "fkcore"] + args, cwd=GAME, env=env,
                              input=data).returncode
        if footer:
            subprocess.run([sys.executable, "-m", "fkcore", "poll", "."], cwd=GAME, env=env)
        return code
    cmd = (f"cd {shlex.quote(cfg['host_game'])} && FK_LINK=on "
           f"PYTHONPATH={shlex.quote(cfg['host_toolkit'])} python3 -m fkcore "
           + " ".join(shlex.quote(a) for a in args))
    if footer:
        cmd += f"; s=$?; PYTHONPATH={shlex.quote(cfg['host_toolkit'])} FK_LINK=on python3 -m fkcore poll .; exit $s"
    return _ssh(cfg, cmd, data=data).returncode


def footer(cfg):
    return remote(cfg, ["poll", "."], footer=False)


def _script():
    """The run's build script: ``<surface>.build.fkb`` of the play-mode surface file in game\\,
    else the first. 2.0.3: the first alone let a ``lab.build.fkb`` copied into game\\ take every
    ``fk build`` of nauvis (it comes first alphabetically)."""
    found = sorted(f for f in os.listdir(GAME) if f.endswith(".build.fkb"))
    if not found:
        sys.exit("fk: no <surface>.build.fkb in game\\")
    for f in sorted(os.listdir(GAME)):
        if not f.endswith(".surface") or f[:-len(".surface")] + ".build.fkb" not in found:
            continue
        try:
            with open(os.path.join(GAME, f), encoding="utf-8") as fh:
                m = re.search(r"^\s*mode\s+(\w+)", fh.read(), re.M)
        except OSError:
            continue
        if (m.group(1) if m else "play") == "play":
            return f[:-len(".surface")] + ".build.fkb"
    return found[0]


def _steps(script):
    names = []
    with open(os.path.join(GAME, script), encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].split()
            if line:
                names.append(f"cover_{line[1]}" if line[0] == "cover" and len(line) > 1 else line[0])
    return names


def _at(names, spec):
    """The index of ``spec`` in the script's steps: NAME, or NAME:K for its K-th time."""
    name, _, k = spec.partition(":")
    where = [i for i, n in enumerate(names) if n == name]
    try:
        k = int(k or 1)
        if k < 1:
            raise ValueError(k)
        return where[k - 1]
    except (ValueError, IndexError):
        sys.exit(f"fk: --from/--to names a step of the script, NAME or NAME:K: {', '.join(names)}")


def _spec(names, i):
    """The step at ``i`` as --from/--to name it (NAME:K when the script runs it more than once)."""
    k = names[:i + 1].count(names[i])
    return names[i] if names.count(names[i]) == 1 else f"{names[i]}:{k}"


def build(cfg, args):
    """Design here up to write_layout, then the game steps (diff, apply) on the host."""
    script = _script()
    names = _steps(script)
    i = _at(names, args[args.index("--from") + 1]) if "--from" in args else 0
    j = _at(names, args[args.index("--to") + 1]) if "--to" in args else len(names) - 1
    link_at = [k for k, n in enumerate(names) if n in LINK_STEPS]
    split = link_at[0] if link_at else len(names)
    code = 0
    if i < split:
        _avail_first(cfg)
        code = local(cfg, ["build", script, "--from", _spec(names, i),
                           "--to", _spec(names, min(j, split - 1))])
    if code == 0 and j >= split:
        push(cfg)
        code = remote(cfg, ["build", script, "--from", _spec(names, max(i, split)),
                            "--to", _spec(names, j)], footer=False)
        pull(cfg)
    else:
        push(cfg)
    return code


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cfg = _config()
    cmd, rest = argv[0], argv[1:]
    if not os.path.exists(STAMP) and cfg["host"] != "local":
        pull(cfg)                          # first use: start from the host's copy
    if cmd == "build":
        if "-h" in rest or "--help" in rest:
            # the help, not a build (the first lead run's worker, 2026-10-21: `fk build --help`
            # ran all 19 steps, the paste included)
            print("fk build [--from STEP] [--to STEP]: the steps of game\\<surface>.build.fkb in "
                  "order, design here and the game steps on the host; STEP is a step's name, or "
                  "NAME:K for its K-th time (docs\\TOOLKIT.md, \"The build script\")")
            return 0
        with _build_lock():
            code = build(cfg, rest)
        footer(cfg)
        return code
    if cmd == "look":
        if "--design" in rest:
            rest = [a for a in rest if a != "--design"]
            code = local(cfg, ["look", ".", "--source", "design"] + _area(rest))
            footer(cfg)
            return code
        push(cfg)
        code = remote(cfg, ["look", ".", "--source", "world"] + _area(rest))
        pull(cfg)
        return code
    if cmd == "wait":
        if "-h" in rest or "--help" in rest:
            print("fk wait 90s | fk wait built [AREA] [--name ENTITY[,...]] [--max 5m] [--poll "
                  "10s]: the one way to wait, from the run's fixed wait budget; it asks first "
                  "(run it again, or add --sure). built: until the area has no ghosts left (or "
                  "the named entity's are gone), or the bound expires; 0 clear, 1 ghosts left, "
                  "2 a link error or no budget left (docs\\TOOLKIT.md, \"The loop\")")
            return 0
        return wait(cfg, rest)
    if cmd == "stage":
        code = local(cfg, ["stage", "."] + rest)
        footer(cfg)
        return code
    if cmd == "lab":
        if "-h" in rest or "--help" in rest:
            print("fk lab NAME [--from DIR] [--size WxH]: NAME (a factory of game\\, or of DIR: a "
                  "stage folder, a scratch copy) built on its own slot of the lab surface, powered "
                  "and stocked; fk lab NAME --measure 60: what it makes there; fk lab NAME --clear; "
                  "fk lab --list (docs\\TOOLKIT.md, \"The lab\")")
            return 0
        if "--from" in rest and cfg["host"] != "local":
            i = rest.index("--from")
            if i + 1 >= len(rest) or not _ship(cfg, rest[i + 1]):
                return 2
        push(cfg)
        code = remote(cfg, ["lab", "."] + rest)
        pull(cfg)
        return code
    if cmd in LOCAL:
        code = local(cfg, [cmd] + rest)
        push(cfg)
        footer(cfg)
        return code
    if cmd == "lua":
        return lua(cfg, rest)
    if cmd in AREA_FIRST:
        rest = _area(rest)
    if cmd in HOST:
        push(cfg)
        code = remote(cfg, [cmd] + ([] if cmd == "say" else ["."]) + rest,
                      footer=cmd not in ("poll", "chat"))
        pull(cfg)
        return code
    print(f"fk: unknown command {cmd!r} (fk --help)", file=sys.stderr)
    return 2


#: run folders ``fk lab --from`` never sends (they are the run's own, or the host's)
_NOT_SENT = ("game", "lab", "bin", ".toolkit", ".loop", ".stage", ".claude", "reports")


def _ship(cfg, rel):
    """``fk lab --from DIR``: DIR (inside the run) to the host's copy of the run, so the lab
    builds what is here. It replaces the host's copy of DIR and nothing else."""
    src = os.path.normpath(os.path.join(RUN, rel))
    parts = os.path.relpath(src, RUN).replace("\\", "/").split("/")
    if os.path.commonpath([src, RUN]) != RUN or parts[0] in (".", "..") + _NOT_SENT \
            or not os.path.isdir(src):
        print(f"fk lab: --from {rel}: a folder of the run with your design in it, such as "
              f"stages\\3 or scratch\\mall (not {parts[0]})", file=sys.stderr)
        return False
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for root, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d not in ("out", ".git"))
            for f in sorted(files):
                full = os.path.join(root, f)
                tar.add(full, arcname=os.path.relpath(full, src).replace("\\", "/"))
    dst = posixpath.join(posixpath.dirname(cfg["host_game"].rstrip("/")), "/".join(parts))
    q = shlex.quote(dst)
    r = _ssh(cfg, f"rm -rf {q} && mkdir -p {q} && tar -xf - -C {q}", data=buf.getvalue())
    if r.returncode:
        print(f"fk lab: sending {rel} to {cfg['host']} failed", file=sys.stderr)
    return r.returncode == 0


def lua(cfg, rest):
    """``fk lua CODE`` or ``fk lua --file F`` (the player's file, anywhere): the chunk goes to the
    host's ``fkcore lua . --file -`` on stdin, so its size and quotes never meet a command line."""
    if "--file" in rest:
        i = rest.index("--file")
        if i + 1 >= len(rest):
            print("fk: lua --file needs a file", file=sys.stderr)
            return 2
        with open(rest[i + 1], encoding="utf-8") as fh:
            code = fh.read()
    else:
        code = " ".join(rest)
    push(cfg)
    rc = remote(cfg, ["lua", ".", "--file", "-"], data=code.encode("utf-8"))
    pull(cfg)
    return rc


def _area(rest):
    """``fk look X0,Y0,X1,Y1`` or ``--area X0,Y0,X1,Y1`` -> the fkcore arguments."""
    if rest and not rest[0].startswith("--"):
        return ["--area", rest[0]] + rest[1:]
    return rest


#: The run's wait budget (2.0.12, Rory 2026-10-24): `fk wait` is the one way to wait, and a run
#: has this many minutes of it. RUN\wait-budget.json keeps what is spent; a "budget_min" written
#: there wins over this number.
WAIT_BUDGET_MIN = 30
WAIT_FILE = os.path.join(RUN, "wait-budget.json")
#: the same wait asked again within this many seconds is the answer "yes"
ASK_AGAIN_S = 120
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(h|min|m|s)")


def _seconds(text):
    m = _DURATION.fullmatch((text or "").strip())
    if not m:
        return None
    return float(m.group(1)) * {"h": 3600, "min": 60, "m": 60, "s": 1}[m.group(2)]


def _budget(settle=True, clock=time.time):
    """The wait budget: {budget_min, spent_s, ...}. A wait that was cut off (its process killed:
    a tool timeout) counts what it ran, up to what it was for (``settle``; the wait that wrote it
    counts itself)."""
    try:
        with open(WAIT_FILE, encoding="utf-8") as fh:
            b = json.load(fh)
    except (OSError, ValueError):
        b = {}
    b.setdefault("budget_min", WAIT_BUDGET_MIN)
    b.setdefault("spent_s", 0.0)
    cut = b.pop("running", None)
    if settle and isinstance(cut, dict):
        b["spent_s"] += max(0.0, min(clock() - cut.get("since", clock()), cut.get("for", 0.0)))
    return b


def _save_budget(b):
    with open(WAIT_FILE + ".new", "w", encoding="utf-8") as fh:
        json.dump(b, fh, indent=1, sort_keys=True)
    os.replace(WAIT_FILE + ".new", WAIT_FILE)


def _left(b):
    return max(0.0, b["budget_min"] * 60 - b["spent_s"])


def wait(cfg, rest, clock=time.time, sleep=time.sleep):
    """``fk wait 90s`` or ``fk wait built ...`` from the run's wait budget (2.0.12). The first
    time it asks; the same wait again within ASK_AGAIN_S seconds, or ``--sure``, waits. It
    spends the time it waited, and with nothing left it refuses. ``built`` waits on the host at
    most what is left."""
    sure = "--sure" in rest
    rest = [a for a in rest if a != "--sure"]
    plain = len(rest) == 1 and _seconds(rest[0]) is not None
    if not plain and rest[:1] != ["built"]:
        print("fk wait 90s, or fk wait built [AREA] [--max 5m] (fk wait --help)", file=sys.stderr)
        return 2
    b = _budget(clock=clock)
    left = _left(b)
    if left <= 0:
        _save_budget(b)
        print(f"fk wait: the run's {b['budget_min']:g} min of wait budget is spent. Look, check "
              "or plan instead.")
        return 2
    asked = " ".join(rest)
    if not sure and not (b.get("asked") == asked
                         and clock() - b.get("asked_at", 0) < ASK_AGAIN_S):
        b["asked"], b["asked_at"] = asked, clock()
        _save_budget(b)
        print(f"Are you sure you want to wait? {left / 60:.0f} min of wait budget left. Run it "
              "again (or add --sure) to wait.")
        return 1
    b.pop("asked", None)
    b.pop("asked_at", None)
    t0 = clock()
    if plain:
        want = min(_seconds(rest[0]), left)
        b["running"] = {"since": t0, "for": want}
        _save_budget(b)
        sleep(want)
        code = 0
    else:
        args = _wait_args(rest)
        if "--max" in args:
            i = args.index("--max")
            want = min(_seconds(args[i + 1]) or 300.0, left) if i + 1 < len(args) else left
            args = args[:i] + args[i + 2:]
        else:
            want = min(300.0, left)
        args += ["--max", f"{int(want)}s"]
        b["running"] = {"since": t0, "for": want}
        _save_budget(b)
        push(cfg)
        code = remote(cfg, ["wait", "."] + args)
        pull(cfg)
    b = _budget(settle=False)
    took = clock() - t0
    b["spent_s"] += took
    _save_budget(b)
    print(f"fk wait: waited {took:.0f} s; {_left(b) / 60:.0f} min of wait budget left")
    return code


#: ``fk wait built`` takes the area where look does, after the word ``built``.
_WAIT_AREA = re.compile(r"-?\d+,-?\d+,-?\d+,-?\d+")


def _wait_args(rest):
    """``fk wait built X0,Y0,X1,Y1 ...`` -> ``built --area X0,Y0,X1,Y1 ...`` (fkcore's ``wait``
    has no positional area, so a negative coordinate never reads as an option)."""
    if len(rest) > 1 and rest[0] == "built" and _WAIT_AREA.fullmatch(rest[1]):
        return ["built", "--area", rest[1]] + rest[2:]
    return rest


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
