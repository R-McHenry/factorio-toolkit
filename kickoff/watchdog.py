"""The player loop's watchdog (2.0.12): it opens a run's play.cmd again when the loop has died.

    python watchdog.py RUN [--quiet 15] [--every 60] [--detach]

The solo run (2026-10-22 22:40): the loop's process went away without a line in play.log, and the
game ran 10.6 hours with nobody playing until the supervising session noticed at 09:18. Every
--every seconds the watchdog looks at RUN. When the loop should run (no STOP file, GOAL.md has
text), play.log has been silent for --quiet minutes and no loop process holds
RUN\\claude-loop.lock (a quiet loop is still a loop: a long build, a usage-limit backoff), it opens
play.cmd again in a window of its own and says so in one line each:
- in play.log, for the record;
- in the game chat (``fkcore say`` through the run's toolkit, as [agent]), for Rory;
- in RUN\\INBOX-watchdog.md, for the player: the loop's first round hands it over.
A restart the loop doesn't come back from doubles the wait before the next one (15, 30, 60, then
every 120 minutes). A loop that ended on its own (its --hours or --rounds) is started again too:
a STOP file is the way to end a run, and it ends the watchdog as well; the next loop start
brings a new one.

claude_loop.py starts it as the loop starts, with --detach: that starts the watchdog again as a
process of its own (no console, a process group of its own, out of any job that allows it) and
returns, so the watchdog's parent is gone and neither a closed window nor a killed process tree
takes it along. One watchdog per run (RUN\\.loop\\watchdog.lock); its own lines go to
RUN\\.loop\\watchdog.log. While it runs it keeps the laptop awake, as the loop does. Stdlib only.
"""
import argparse
import atexit
import ctypes
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime

QUIET = 15        # minutes play.log is silent, with no loop running, before the watchdog restarts it
EVERY = 60        # seconds between two looks
LONGEST = 120     # minutes: the longest wait after restarts the loop didn't come back from


def running(pid, since=None):
    """Is ``pid`` a live Python process, created no later than ``since`` (an epoch time) when that
    is given? Windows gives a dead process's id to new processes: one younger than the lock file
    that names it is not the process that wrote it."""
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
        except OSError:
            return False
        return True
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    h = ctypes.c_void_p(h)
    try:
        code = ctypes.c_ulong()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:   # STILL_ACTIVE
            return False
        name, size = ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
        if k.QueryFullProcessImageNameW(h, 0, name, ctypes.byref(size)) and \
                not os.path.basename(name.value).lower().startswith("python"):
            return False
        if since is not None:
            times = [ctypes.c_ulonglong() for _ in range(4)]       # FILETIMEs: 100 ns since 1601
            if k.GetProcessTimes(h, *(ctypes.byref(t) for t in times)):
                if (times[0].value - 116444736000000000) / 1e7 > since:
                    return False
        return True
    finally:
        k.CloseHandle(h)


def holder(path):
    """The pid a lock file names while that process still runs (``running``), or None."""
    try:
        with open(path) as f:
            pid = int(f.read().strip() or 0)
        since = os.path.getmtime(path) + 5             # a few seconds of clock between the two
    except (OSError, ValueError):
        return None
    return pid if pid and running(pid, since) else None


def open_play(path):
    """play.cmd in a window of its own, as the kickoff opens it: explorer starts it, so it is
    nobody's child here."""
    subprocess.Popen(["explorer.exe", path])


def say_in_game(run, text):
    """One line in the game chat through the run's own toolkit (``fkcore say``), as fk does it:
    on the game host over ssh, or here for a laptop server (run.json host "local")."""
    with open(os.path.join(run, "run.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("host") == "local":
        env = dict(os.environ, FK_LINK="on", PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=os.path.join(run, ".toolkit"),
                   **{k: v for k, v in (cfg.get("env") or {}).items() if v})
        r = subprocess.run([sys.executable, "-m", "fkcore", "say", text],
                           cwd=os.path.join(run, "game"), env=env, capture_output=True, text=True,
                           timeout=30)
    else:
        cmd = (f"cd {shlex.quote(cfg['host_game'])} && FK_LINK=on "
               f"PYTHONPATH={shlex.quote(cfg['host_toolkit'])} timeout 15 python3 -m fkcore say "
               + shlex.quote(text))
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", cfg["host"], cmd], capture_output=True,
                           text=True, timeout=30)
    return r.returncode == 0


class Watchdog:
    def __init__(self, run, quiet=QUIET, opener=open_play, say=say_in_game):
        self.run, self.quiet = run, quiet * 60
        self.opener, self.say = opener, say
        self.failed = 0         # restarts in a row the loop has not come back from
        self.mark = None        # play.log's time just after the last restart's line

    def path(self, *parts):
        return os.path.join(self.run, *parts)

    def note(self, text):
        """A line of the watchdog's own (RUN\\.loop\\watchdog.log)."""
        with open(self.path(".loop", "watchdog.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")

    def look(self, now=None):
        """One look -> "stop" (a STOP file), "restarted", or None."""
        now = time.time() if now is None else now
        if os.path.exists(self.path("STOP")):
            return "stop"
        try:
            with open(self.path("GOAL.md"), encoding="utf-8", errors="replace") as f:
                if not f.read().strip():
                    return None                  # the loop pauses on an empty goal: so do we
            last = os.path.getmtime(self.path("play.log"))
        except OSError:
            return None
        if self.mark is not None and last > self.mark + 1:
            self.failed, self.mark = 0, None     # the loop wrote since the restart: it came back
        misses = self.failed + (self.mark is not None)
        if now - last < min(self.quiet * 2 ** misses, LONGEST * 60):
            return None
        if holder(self.path("claude-loop.lock")):
            return None
        self.restart(last, now)
        self.failed, self.mark = misses, os.path.getmtime(self.path("play.log"))
        return "restarted"

    def restart(self, last, now):
        went, at = f"{datetime.fromtimestamp(last):%H:%M}", f"{datetime.fromtimestamp(now):%H:%M}"
        with open(self.path("play.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.fromtimestamp(now):%H:%M:%S}  watchdog: play.log silent since "
                    f"{went} and no loop running: play.cmd started again\n")
        with open(self.path("INBOX-watchdog.md"), "a", encoding="utf-8") as f:
            f.write(f"Your loop stopped around {went} and the watchdog started it again at {at}. "
                    "The game ran on meanwhile, so look around before you carry on.\n")
        try:
            self.opener(self.path("play.cmd"))
        except OSError as exc:
            self.note(f"could not open play.cmd: {exc}")
        try:
            said = self.say(self.run, f"watchdog: the player's loop stopped around {went}; "
                                      f"started it again at {at}.")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            said = f"{type(exc).__name__}: {exc}"
        self.note(f"restarted play.cmd (silent since {went}); game chat: "
                  f"{'said' if said is True else said or 'failed'}")


def detach(run, quiet, every):
    """This watchdog again as a process of its own, and return: the process that ran this exits at
    once, so the watchdog is nobody's child (a tree kill of the loop's window doesn't reach it)
    and it has no console (closing one doesn't either)."""
    os.makedirs(os.path.join(run, ".loop"), exist_ok=True)
    args = [sys.executable, os.path.abspath(__file__), run, "--quiet", f"{quiet:g}",
            "--every", f"{every:g}"]
    with open(os.path.join(run, ".loop", "watchdog.log"), "a", encoding="utf-8") as log:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, and CREATE_BREAKAWAY_FROM_JOB when the job
        # allows it (CreateProcess refuses it otherwise)
        for flags in ((0x00000008 | 0x00000200 | 0x01000000, 0x00000008 | 0x00000200)
                      if os.name == "nt" else (0,)):
            try:
                subprocess.Popen(args, cwd=run, creationflags=flags, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, close_fds=True,
                                 start_new_session=os.name != "nt")
                return 0
            except OSError:
                continue
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="the player loop's watchdog")
    ap.add_argument("run")
    ap.add_argument("--quiet", type=float, default=QUIET, help="minutes")
    ap.add_argument("--every", type=float, default=EVERY, help="seconds")
    ap.add_argument("--detach", action="store_true", help="start it as a process of its own")
    a = ap.parse_args(argv)
    run = os.path.abspath(a.run)
    if a.detach:
        return detach(run, a.quiet, a.every)
    os.makedirs(os.path.join(run, ".loop"), exist_ok=True)
    lock = os.path.join(run, ".loop", "watchdog.lock")
    if holder(lock) not in (None, os.getpid()):
        return 0                                 # one watchdog per run
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: holder(lock) == os.getpid() and os.remove(lock))
    if os.name == "nt":
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: a dead loop no longer keeps the laptop awake
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    dog = Watchdog(run, a.quiet)
    dog.note(f"watchdog {os.getpid()}: restarts play.cmd after {a.quiet:g} min of silence in "
             "play.log with no loop running; a STOP file ends it")
    while True:
        try:
            what = dog.look()
        except Exception as exc:  # the watchdog outlives its own mistakes
            dog.note(f"look: {type(exc).__name__}: {exc}")
            what = None
        if what == "stop":
            dog.note("STOP file: the watchdog ends")
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
