"""fk: the agent's one command, on the laptop. The game host is an implementation detail.

A run folder holds ``game\\`` (the game codebase the agent edits: ``.fk`` modules, the surface file,
the build script), ``bin\\`` (this file and ``fk.cmd``), ``.toolkit\\`` (the toolkit, pinned for the
run) and ``run.json``, which names the game host, the host's copy of the run and the host's
toolkit (also pinned: files a running session uses never change under it). Each command:

1. runs where it belongs. Design and every pure command run here, where the CPU is (elaborate,
   rates, place, route, cover, floorplan, checks, write_layout). Whatever reads or writes the game
   runs on the host, where RCON is: diff, apply, a live look, measure, alerts, stats, chart,
   terrain, chat.
2. keeps the two copies of ``game\\`` in step: what changed here is pushed before a host step, and
   what the host wrote is pulled after it. Changed means content (``out\\.synced`` keeps each
   file's hash at the last sync), a pull keeps a file edited here since (the next push sends
   it), and the syncs of two fk commands take turns (1.4.2: a player's background ``fk look``
   loop pulled the host's copy over fresh edits, which the next push then skipped by mtime).
3. ends with the footer, ``fkcore poll``: chat lines that are new since the last command, and the
   game's new alerts and reminders.

``fk build`` splits the flow at ``write_layout``: design here (``--to write_layout``), then on the
host the steps after it (``--from diff``: the floorplan is replayed on the checkpoints). Stdlib
only. ``FK_RUN`` names the run folder (default: the folder above this file's).

``fk lua`` sends its chunk (the argument, or ``--file F``'s text) over the ssh's stdin, never on
the command line (1.2): Git for Windows' ssh, an MSYS program, gets at most about 8 kB of one
argument, so a 13 kB chunk arrived cut, and its open single quote stopped the host's shell.

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
import shlex
import subprocess
import sys
import tarfile
import time

RUN = os.path.abspath(os.environ.get("FK_RUN") or os.path.join(os.path.dirname(__file__), ".."))
GAME = os.path.join(RUN, "game")
STAMP = os.path.join(GAME, "out", ".synced")

#: commands that are pure: they run here, on the run's own toolkit
LOCAL = {"rates", "check", "explain", "unfold", "render", "layout", "split-to-chest", "merge",
         "insert", "chests-to-net", "net-to-chests"}
#: commands that need the game: they run on the host, with the link on
HOST = {"chat", "say", "poll", "alerts", "stats", "chart", "read-terrain", "measure", "adopt",
        "sense", "research", "tech", "recipes", "lua", "fresh"}
#: host commands whose first word may be the area, as for look: ``fk fresh X0,Y0,X1,Y1``
AREA_FIRST = ("fresh", "measure")
#: files only the host writes: pulled, never pushed
HOST_MADE = ("out/.synced", "out/chat-cursor.json", "out/alerts.json", "out/inbox.txt")
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
    found = sorted(f for f in os.listdir(GAME) if f.endswith(".build.fkb"))
    if not found:
        sys.exit("fk: no <surface>.build.fkb in game\\")
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
