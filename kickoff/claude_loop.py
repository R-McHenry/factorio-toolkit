"""The goal loop for a Claude Code player: launch.ps1's loop, with claude instead of dsh.

    python C:\\fk-player\\claude_loop.py C:\\fk-player\\runs\\<run> [--hours 24] [--rounds 500]
           [--turn-cap 120] [--model claude-opus-5-5] [--note TEXT]

One conversation per run: its id is kept in <run>\\claude-session.txt, so starting the loop again
continues it. Round 1 sends launch.json's first message (plus --note); every later round sends
GOAL.md, as the brief promises ("Whenever you finish a turn, its text comes back to you as the
next message"). The loop stops when <run>\\STOP exists (a running turn is stopped too), when
GOAL.md is empty or missing, or after --rounds rounds or --hours hours. A turn past --turn-cap
minutes is stopped and the next round says so. A failed round (usage limit, network) waits and
retries: 2, 5, 10, 20, then every 30 minutes; it does not count as a round.

Claude Code must be signed in on its own (the app's sign-in does not carry over to a standalone
claude.exe): when it is not, the loop runs `claude auth login` in its window first.

The player runs headless in auto mode, the permission mode of the app sessions: the auto mode
classifier decides each action, and one it refuses comes back to the player as an error (nothing
waits for an answer). No MCP servers. This window and <run>\\play.log show what it does;
<run>\\claude-events.jsonl has the raw events.
"""
import argparse
import atexit
import ctypes
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

MODEL = "claude-opus-5-5"
BACKOFF = [2, 5, 10, 20, 30]  # minutes, after the 1st, 2nd, ... failed round in a row
MIN_ROUND = 60                # seconds: a quicker round waits out the rest before the next one


def claude_bin():
    """The newest claude.exe the desktop app keeps (looked up each round: the app updates it). The
    app is an MSIX package: outside it, its %APPDATA%\\Claude is under %LOCALAPPDATA%\\Packages."""
    def version(p):
        return [int(x) if x.isdigit() else 0 for x in p.split(os.sep)[-3].split(".")]
    pats = [r"%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code\*\*\claude.exe",
            r"%APPDATA%\Claude\claude-code\*\*\claude.exe"]
    found = sorted({p for pat in pats for p in glob.glob(os.path.expandvars(pat))}, key=version)
    if found:
        return found[-1]
    return shutil.which("claude") or sys.exit("no claude.exe found")


def child_env(run):
    """This environment without what an app session sets (its per-session auth proxy and session
    ids: the player uses its own sign-in, so it outlives the session that started it), with the
    run's bin first on PATH."""
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith(("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CLAUDE_PREVIEW_"))
                   or k in ("CLAUDECODE", "CLAUDE_PROJECT_DIR"))}
    env["PATH"] = os.path.join(run, "bin") + os.pathsep + env.get("PATH", "")
    return env


def short(s, n=300):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "~"


class Log:
    def __init__(self, run):
        self.f = open(os.path.join(run, "play.log"), "a", encoding="utf-8")

    def __call__(self, text):
        line = f"{datetime.now():%H:%M:%S}  {text}"
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()


def tool_line(name, inp):
    if name == "Bash":
        return "$ " + short(inp.get("command", ""), 240)
    if name == "PowerShell":
        return "PS> " + short(inp.get("command", ""), 240)
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return f"{name.lower()} {inp.get('file_path', '')}"
    if name in ("Grep", "Glob"):
        return f"{name.lower()} {short(inp.get('pattern', ''), 120)}"
    if name in ("Agent", "Task"):
        return "agent: " + short(inp.get("description", ""), 120)
    return f"{name} {short(json.dumps(inp), 160)}"


def feed(ev, log, state):
    """One stream-json event: keep the session id and the result, show text and tool calls."""
    if ev.get("session_id"):
        state["sid"] = ev["session_id"]
    pad = "    " if ev.get("parent_tool_use_id") else ""
    t = ev.get("type")
    if t == "assistant":
        for c in ev.get("message", {}).get("content", []):
            if c.get("type") == "text" and c.get("text", "").strip():
                log(pad + "> " + short(c["text"], 500))
            elif c.get("type") == "tool_use":
                state["tools"] += 1
                log(pad + tool_line(c.get("name", "?"), c.get("input") or {}))
    elif t == "user":
        content = ev.get("message", {}).get("content", [])
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error"):
                body = c.get("content")
                if isinstance(body, list):
                    body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                log(pad + "  ! " + short(body, 200))
    elif t == "result":
        state["result"] = ev


def turn(run, sid, text, model, cap_min, log, events):
    """One claude -p turn on the run's conversation -> (state, exit code, why it was cut short)."""
    cmd = [claude_bin(), "-p", "--output-format", "stream-json", "--verbose", "--model", model,
           "--permission-mode", "auto", "--strict-mcp-config"]
    if sid:
        cmd += ["--resume", sid]
    state = {"sid": sid, "tools": 0, "result": None}
    err = open(os.path.join(run, "claude-loop-stderr.log"), "a", encoding="utf-8")
    p = subprocess.Popen(cmd, cwd=run, env=child_env(run), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=err)

    def pump():
        for raw in p.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            events.write(line + "\n")
            events.flush()
            try:
                feed(json.loads(line), log, state)
            except ValueError:
                log("  " + short(line, 200))
            except Exception as exc:  # a feed bug never stops the player
                log(f"  (feed: {type(exc).__name__}: {exc})")

    th = threading.Thread(target=pump, daemon=True)
    th.start()
    p.stdin.write(text.encode("utf-8"))
    p.stdin.close()
    deadline, cut = time.time() + cap_min * 60, None
    while p.poll() is None:
        if os.path.exists(os.path.join(run, "STOP")):
            cut = "STOP"
        elif time.time() > deadline:
            cut = "cap"
        if cut:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            p.wait()
            break
        time.sleep(5)
    th.join(timeout=10)
    err.close()
    return state, p.returncode, cut


def ensure_login(run, log):
    def logged_in():
        out = subprocess.run([claude_bin(), "auth", "status"], env=child_env(run),
                             capture_output=True, text=True)
        try:
            return bool(json.loads(out.stdout).get("loggedIn"))
        except ValueError:
            return False
    while not logged_in():
        log("Claude Code is not signed in on this laptop: sign in through the browser that opens.")
        subprocess.run([claude_bin(), "auth", "login"], env=child_env(run))
    log("Claude Code is signed in")


def lock(run):
    path = os.path.join(run, "claude-loop.lock")
    if os.path.exists(path):
        pid = open(path).read().strip()
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True).stdout.lower()
        if pid and pid in out and "python" in out:
            sys.exit(f"a loop already plays this run (pid {pid}): close that window first")
    with open(path, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(path) and os.remove(path))


def main():
    ap = argparse.ArgumentParser(description="the goal loop for a Claude Code player")
    ap.add_argument("run")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--rounds", type=int, default=500)
    ap.add_argument("--turn-cap", type=float, default=120, help="minutes")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--note", default="", help="a paragraph added to the first message")
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lock(run)
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: the laptop does not sleep while the loop plays
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    log = Log(run)
    events = open(os.path.join(run, "claude-events.jsonl"), "a", encoding="utf-8")
    ensure_login(run, log)
    sid_file = os.path.join(run, "claude-session.txt")
    sid = open(sid_file).read().strip() if os.path.exists(sid_file) else ""
    with open(os.path.join(run, "launch.json"), encoding="utf-8") as f:
        first = json.load(f)["first"] + (f"\n\n{a.note}" if a.note else "")
    goal_path, stop_path = os.path.join(run, "GOAL.md"), os.path.join(run, "STOP")
    end = time.time() + a.hours * 3600
    n, fails, cut = 0, 0, None
    log(f"loop start: {run}, {a.model}, conversation {sid or 'new'}; it stops on a STOP file, "
        f"an empty GOAL.md, {a.rounds} rounds or {a.hours:g} h")
    while True:
        goal = open(goal_path, encoding="utf-8").read().strip() if os.path.exists(goal_path) else ""
        why = ("STOP file" if os.path.exists(stop_path) else
               "GOAL.md is empty" if sid and not goal else
               f"{a.rounds} rounds" if n >= a.rounds else
               f"{a.hours:g} h" if time.time() > end else None)
        if why:
            log(f"stopped: {why}")
            break
        if sid:
            text = (f"[GOAL.md, round {n + 1}. This message is the text of GOAL.md in your folder: "
                    f"edit that file to change what it says next time, or empty it to stop "
                    f"playing.]\n\n{goal}")
        else:
            text = first
        if cut == "cap":
            text = (f"Your last turn was stopped after {a.turn_cap:g} minutes (the loop's cap on one "
                    f"turn). Carry on from where it was cut off.\n\n{text}")
        n += 1
        log(f"=== round {n} ({'conversation ' + sid[:8] if sid else 'new conversation'})")
        t0 = time.time()
        state, rc, cut = turn(run, sid, text, a.model, a.turn_cap, log, events)
        if state["sid"] and state["sid"] != sid:
            sid = state["sid"]
            with open(sid_file, "w") as f:
                f.write(sid)
        res, mins = state["result"] or {}, (time.time() - t0) / 60
        if cut:
            log(f"=== round {n} cut short ({cut}) after {mins:.0f} min, {state['tools']} tool calls")
            fails = 0
            continue
        if res and not res.get("is_error"):
            fails = 0
            log(f"=== round {n} done: {mins:.1f} min, {res.get('num_turns')} steps, "
                f"{state['tools']} tool calls, ${res.get('total_cost_usd') or 0:.2f}")
            if res.get("result"):
                log("turn report: " + short(res["result"], 1500))
            time.sleep(max(0, MIN_ROUND - (time.time() - t0)))
            continue
        msg = short(res.get("result") or res.get("subtype") or
                    f"exit code {rc}, no result (claude-loop-stderr.log has the error)", 300)
        if "No conversation found" in msg:
            sid = ""
        delay = BACKOFF[min(fails, len(BACKOFF) - 1)]
        fails += 1
        n -= 1
        log(f"=== round failed: {msg}; trying again in {delay} min")
        wake = time.time() + delay * 60
        while time.time() < wake and not os.path.exists(stop_path):
            time.sleep(10)


if __name__ == "__main__":
    main()
