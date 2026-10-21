"""The goal loop for a Claude Code player: launch.ps1's loop, with claude instead of dsh.

    python C:\\fk-player\\claude_loop.py C:\\fk-player\\runs\\<run> [--hours 24] [--rounds 500]
           [--turn-cap 120] [--model claude-opus-5-5] [--note TEXT]

One conversation per run: its id is kept in <run>\\claude-session.txt, so starting the loop again
continues it. Round 1 sends launch.json's first message (plus --note); every later round sends
GOAL.md, as the brief promises ("Whenever you finish a turn, its text comes back to you as the
next message"). The loop stops when <run>\\STOP exists (a running turn is stopped too)
or after --rounds rounds or --hours hours; while GOAL.md is empty or missing it pauses
(2026-10-21) and resumes when GOAL.md has text again. A turn past --turn-cap
minutes is stopped and the next round says so. A failed round (usage limit, network) waits and
retries: 2, 5, 10, 20, then every 30 minutes; it does not count as a round.

Claude Code must be signed in on its own (the app's sign-in does not carry over to a standalone
claude.exe): when it is not, the loop runs `claude auth login` in its window first.

The player runs headless in auto mode, the permission mode of the app sessions: the auto mode
classifier decides each action, and one it refuses comes back to the player as an error (nothing
waits for an answer). No MCP servers. This window and <run>\\play.log show what it does;
<run>\\claude-events.jsonl has the raw events.

What the player must not miss reaches it after its next shell command, whatever that command's
output kept (the 0534 player cut fk's footer off 199 of 245 times and never saw Rory's chat): a
watcher reads the game every 30 s and notes game chat and <run>\\INBOX.md (a message for the
player: the file is taken and moved into .loop), each once; and it keeps the world line in
.loop\\world.txt (the ghosts that wait and what the network lacks, ghosts no powered roboport
reaches, idle robots, the research),
rewritten when what blocks changes (at most every 2 minutes) or every 10 minutes while something
does. claude_hook.py, a PostToolUse hook, hands over the notes and the world line when it is new;
each round's message starts with them too.
"""
import argparse
import atexit
import ctypes
import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_hook  # noqa: E402  (beside this file: the hook that hands the notes over)

MODEL = "claude-opus-5-5"
BACKOFF = [2, 5, 10, 20, 30]  # minutes, after the 1st, 2nd, ... failed round in a row
MIN_ROUND = 60                # seconds: a quicker round waits out the rest before the next one
WATCH = 30                    # seconds between two reads of the game
REMIND = 600                  # seconds: the world line again while something stays blocked
SETTLE = 120                  # seconds: the world line changes at most this often

#: one free read of the game: the ghosts per item (with the network's stock and whether the
#: recipe is locked), the ghosts outside every powered roboport's construction area (the 2005
#: player's silent deadlock: a re-laid grid left the poles that would join it out of reach), the
#: construction robots, the research, the labs that wait for packs and what their packs' makers
#: lack (2026-10-21: both players' research stood on one starved pack while the line said 11%),
#: and the game chat after CURSOR
STATUS_LUA = r"""
local s, f = game.surfaces.nauvis, game.forces.player
local net
local boxes = {}
for _, r in pairs(s.find_entities_filtered{type = "roboport", force = f}) do
  if r.logistic_network and not net then net = r.logistic_network end
  local c = r.logistic_cell
  if c and c.transmitting and c.construction_radius > 0 then
    local p, d = r.position, c.construction_radius
    boxes[#boxes + 1] = {p.x - d, p.y - d, p.x + d, p.y + d}
  end
end
local count, far, at = {}, 0, nil
for _, e in pairs(s.find_entities_filtered{type = "entity-ghost", force = f}) do
  local it = e.ghost_prototype.items_to_place_this
  local n = (it and it[1] and it[1].name) or e.ghost_name
  count[n] = (count[n] or 0) + 1
  local p, ok = e.position, false
  for _, b in pairs(boxes) do
    if p.x >= b[1] and p.x <= b[3] and p.y >= b[2] and p.y <= b[4] then ok = true break end
  end
  if not ok then
    far = far + 1
    at = at or {item = n, x = math.floor(p.x), y = math.floor(p.y)}
  end
end
local ghosts = {}
for n, c in pairs(count) do
  local r = f.recipes[n]
  ghosts[#ghosts + 1] = {item = n, ghosts = c, stock = net and net.get_item_count(n) or 0,
                         locked = (r ~= nil and not r.enabled)}
end
local chat = {}
for _, m in pairs(storage.fk_chat or {}) do
  if (m.tick or 0) > CURSOR then chat[#chat + 1] = m end
end
local res = f.current_research
local labs = {n = 0, short = 0, lack = {}, makers = {}}
for _, l in pairs(s.find_entities_filtered{type = "lab", force = f}) do
  labs.n = labs.n + 1
  if res and l.status == defines.entity_status.missing_science_packs then
    labs.short = labs.short + 1
    local inv = l.get_inventory(defines.inventory.lab_input)
    for _, ing in pairs(res.research_unit_ingredients) do
      if inv and inv.get_item_count(ing.name) == 0 then
        labs.lack[ing.name] = (labs.lack[ing.name] or 0) + 1
      end
    end
  end
end
if labs.short > 0 then
  for _, a in pairs(s.find_entities_filtered{type = "assembling-machine", force = f}) do
    local r = a.get_recipe()
    if r and labs.lack[r.name] then
      local m = labs.makers[r.name] or {n = 0, short = 0}
      m.n = m.n + 1
      if a.status == defines.entity_status.item_ingredient_shortage then m.short = m.short + 1 end
      labs.makers[r.name] = m
    end
  end
end
rcon.print(helpers.table_to_json{tick = game.tick, ghosts = ghosts, chat = chat,
  unreached = far > 0 and {n = far, first = at} or nil,
  robots = net and {idle = net.available_construction_robots, all = net.all_construction_robots},
  research = res and {name = res.name, pct = math.floor(f.research_progress * 100)},
  labs = labs})
"""


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
           "--permission-mode", "auto", "--strict-mcp-config", "--settings", settings(run)]
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


def host_status(cfg, cursor, folder=None):
    """The STATUS_LUA read through the run's own toolkit on the game host (no footer: the
    player's alert and chat cursors stay where they are), or None. A local run (a laptop server:
    run.json host "local") reads it here, with the run's link settings."""
    lua = STATUS_LUA.replace("CURSOR", str(int(cursor)))
    if cfg.get("host") == "local":
        env = dict(os.environ, FK_LINK="on", PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=os.path.join(folder, ".toolkit"),
                   **{k: v for k, v in (cfg.get("env") or {}).items() if v})
        r = subprocess.run([sys.executable, "-m", "fkcore", "lua", ".", lua],
                           cwd=os.path.join(folder, "game"), env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
    else:
        cmd = (f"cd {shlex.quote(cfg['host_game'])} && FK_LINK=on "
               f"PYTHONPATH={shlex.quote(cfg['host_toolkit'])} timeout 15 python3 -m fkcore lua . "
               + shlex.quote(lua))
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", cfg["host"], cmd], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
    for line in reversed(r.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def status_line(st):
    """-> (the world line, the key of what blocks: SHORT and LOCKED ghost items, ghosts no
    powered roboport reaches, no research, research stalled with every lab waiting for packs)."""
    gh = sorted(st.get("ghosts") or [], key=lambda g: -g["ghosts"])
    total = sum(g["ghosts"] for g in gh)
    blocked, parts = [], []
    if total:
        items = []
        for g in gh[:8]:
            if g.get("stock"):
                why = f"{g['stock']} in the network"
            elif g.get("locked"):
                why = "LOCKED: the network holds none and its recipe needs research"
                blocked.append(g["item"] + ":locked")
            else:
                why = "SHORT: the network holds none"
                blocked.append(g["item"] + ":short")
            items.append(f"{g['ghosts']} {g['item']} ({why})")
        more = f", and {len(gh) - 8} more kinds" if len(gh) > 8 else ""
        parts.append(f"{total} ghosts wait for the robots: " + ", ".join(items) + more)
        far = st.get("unreached")
        if far:
            at = far.get("first") or {}
            parts.append(f"UNREACHED: {far['n']} of them stand outside every powered roboport's "
                         f"construction area, so no robot will build them (first: "
                         f"{at.get('item')} at {at.get('x')},{at.get('y')})")
            blocked.append("unreached")
    else:
        parts.append("no ghosts wait")
    rb = st.get("robots")
    if rb:
        parts.append(f"construction robots: {rb['idle']} of {rb['all']} idle")
    r = st.get("research")
    if r:
        parts.append(f"research: {r['name']} {r['pct']}%")
        lab = st.get("labs") or {}
        if lab.get("short"):
            # Lua's empty table comes back as a JSON list
            lack = lab.get("lack") if isinstance(lab.get("lack"), dict) else {}
            makers = lab.get("makers") if isinstance(lab.get("makers"), dict) else {}
            stalled = lab["short"] >= lab.get("n", 0)
            text = (f"RESEARCH STALLED: all {lab['n']} labs wait for packs" if stalled else
                    f"{lab['short']} of {lab.get('n')} labs wait for packs")
            if lack:
                text += " (" + ", ".join(f"{p} missing in {k}" for p, k in
                                          sorted(lack.items(), key=lambda kv: -kv[1])) + ")"
            short = [f"{m['short']} of {m['n']} {p} makers short of ingredients"
                     for p, m in sorted(makers.items()) if m.get("short")]
            if short:
                text += "; " + ", ".join(short)
            parts.append(text)
            if stalled:
                blocked.append("labs:stalled")
    else:
        parts.append("RESEARCH: NONE, nothing researches")
        blocked.append("research:none")
    return "; ".join(parts) + ".", ",".join(sorted(blocked))


class Watch(threading.Thread):
    """Every WATCH seconds: INBOX.md, new game chat, and the world line when what blocks changes
    (or every REMIND seconds while something does), as notes for the hook and the next round."""

    def __init__(self, folder, log):
        super().__init__(daemon=True)
        self.folder, self.log = folder, log
        self.dir = os.path.join(folder, ".loop")
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.cfg = cfg
        self.cursor_file = os.path.join(self.dir, "chat-cursor")
        # no cursor yet: the chat so far is not news, the first read only sets the cursor
        self.cursor = int(open(self.cursor_file).read()) if os.path.exists(self.cursor_file) else None
        self.key, self.said = None, 0.0
        self.mutex = threading.Lock()

    def note(self, text):
        with open(os.path.join(self.dir, "notes-pending.txt"), "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")

    def world(self, line):
        """The world line now (one file, rewritten: lines never stack up while the player waits)."""
        path = os.path.join(self.dir, "world.txt")
        with open(path + ".new", "w", encoding="utf-8") as f:
            f.write(f"[World now, {datetime.now():%H:%M}] {line}\n")
        os.replace(path + ".new", path)

    def take(self):
        """The pending notes and the world line if new, for a round's message (claude_hook.take)."""
        with self.mutex:
            return claude_hook.take(self.folder)

    def run(self):
        while True:
            try:
                self.check()
            except Exception as exc:  # the watch never stops the player
                self.log(f"  (watch: {type(exc).__name__}: {short(exc, 200)})")
            time.sleep(WATCH)

    def check(self, world=False):
        """One read; ``world``: note the world line whatever it says (a round's start)."""
        with self.mutex:
            inbox = os.path.join(self.folder, "INBOX.md")
            if os.path.exists(inbox):
                with open(inbox, encoding="utf-8") as f:
                    text = f.read().strip()
                os.replace(inbox, os.path.join(self.dir, f"inbox-{datetime.now():%Y%m%d-%H%M%S}.md"))
                if text:
                    self.note(f"[A message for you, from INBOX.md]\n{text}")
                    self.log("inbox: " + short(text, 300))
            if not self.cfg:
                return
            st = host_status(self.cfg, self.cursor or 0, self.folder)
            if not st:
                return
            if self.cursor is None:
                self.cursor = max([int(m.get("tick", 0)) for m in st.get("chat") or []] + [0])
                with open(self.cursor_file, "w") as f:
                    f.write(str(self.cursor))
                st["chat"] = []
            for m in sorted(st.get("chat") or [], key=lambda m: m.get("tick", 0)):
                self.note(f"[{m.get('name', '?')} in game chat] {m.get('message', '')}\n"
                          '(Answer with fk say "text".)')
                self.log(f"chat {m.get('name', '?')}: {short(m.get('message', ''), 200)}")
                self.cursor = max(self.cursor, int(m.get("tick", 0)))
                with open(self.cursor_file, "w") as f:
                    f.write(str(self.cursor))
            line, key = status_line(st)
            since = time.time() - self.said
            due = (key != self.key and since > SETTLE) or (key and since > REMIND)
            if world or (due and (key or self.key)):
                self.world(line)
                self.log("world: " + line)
                self.said, self.key = time.time(), key


def settings(folder):
    """The --settings file: claude_hook.py after every shell command."""
    hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_hook.py")
    cmd = f'python "{hook}" "{folder}"'.replace("\\", "/")
    path = os.path.join(folder, ".loop", "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"hooks": {"PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [
            {"type": "command", "command": cmd, "timeout": 10}]}]}}, f, indent=1)
    return path


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
    watch = Watch(run, log)
    watch.start()
    end = time.time() + a.hours * 3600
    n, fails, cut = 0, 0, None
    restarted = bool(sid)  # a loop started again on a conversation: its last turn was cut
    log(f"loop start: {run}, {a.model}, conversation {sid or 'new'}; it stops on a STOP file, "
        f"{a.rounds} rounds or {a.hours:g} h, and pauses while GOAL.md is empty")
    paused = False
    while True:
        goal = open(goal_path, encoding="utf-8").read().strip() if os.path.exists(goal_path) else ""
        why = ("STOP file" if os.path.exists(stop_path) else
               f"{a.rounds} rounds" if n >= a.rounds else
               f"{a.hours:g} h" if time.time() > end else None)
        if why:
            log(f"stopped: {why}")
            break
        if sid and not goal:
            # an empty GOAL.md pauses the loop, it no longer ends it (2026-10-21: a player that
            # believed it was stuck emptied it at 01:41 and the night's run stopped): whoever
            # looks in (the lead, Rory) writes a goal again and play resumes on its own
            if not paused:
                log("paused: GOAL.md is empty; play resumes when it has text again (STOP ends it)")
                paused = True
            time.sleep(60)
            continue
        if paused:
            log("resumed: GOAL.md has text again")
            paused = False
        if sid:
            text = (f"[GOAL.md, round {n + 1}. This message is the text of GOAL.md in your folder: "
                    f"edit that file to change what it says next time, or empty it to stop "
                    f"playing.]\n\n{goal}")
        else:
            text = first
        if cut == "cap":
            text = (f"Your last turn was stopped after {a.turn_cap:g} minutes (the loop's cap on one "
                    f"turn). Carry on from where it was cut off.\n\n{text}")
        try:
            watch.check(world=True)
        except Exception as exc:
            log(f"  (watch: {type(exc).__name__}: {short(exc, 200)})")
        notes = watch.take()
        if notes:
            text = f"{notes}\n\n{text}"
        if restarted:
            text = f"The loop restarted and stopped your last turn; carry on from where you were.\n\n{text}"
            restarted = False
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
