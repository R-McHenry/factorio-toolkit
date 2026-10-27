"""The goal loop for a Claude Code player: launch.ps1's loop, with claude instead of dsh.

    python C:\\fk-player\\claude_loop.py C:\\fk-player\\runs\\<run> [--hours 24] [--rounds 500]
           [--turn-cap 120] [--model claude-opus-5-5] [--note TEXT] [--fresh-at 200000]

One conversation per run: its id is kept in <run>\\claude-session.txt, so starting the loop again
continues it. Round 1 sends launch.json's first message (plus --note); every later round sends
GOAL.md, as the brief promises ("Whenever you finish a turn, its text comes back to you as the
next message"). The loop stops when <run>\\STOP exists (a running turn is stopped too)
or after --rounds rounds or --hours hours; while GOAL.md is empty or missing it pauses
(2026-10-21) and resumes when GOAL.md has text again. A round past --turn-cap
minutes ends at its next quiet moment (the player waits and nothing of its runs), and the player
hears so if workers still run; one still busy GRACE minutes later is stopped, workers too, and the
next round says so. A failed round (usage limit, network) waits and
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
player: the file is taken and moved into .loop; INBOX-<name>.md too, one per writer), each
once; and it keeps the world line in .loop\\world.txt (the ghosts that wait and what the network
lacks, ghosts no powered roboport reaches, idle robots, the research), rewritten when what blocks
changes (at most every 2 minutes) or every 10 minutes while something
does. claude_hook.py, a PostToolUse hook, hands over the notes and the world line when it is new;
each round's message starts with them too.

2.0 (Rory, 2026-10-21: a lead player plus worker players). With workers (new_run.py --workers
claude) the player is a lead that hands each design or in-game action to a worker, Claude Code's
`worker` subagent (<run>\\.claude\\agents\\worker.md), and reads back its short report. The
workers' tool calls show indented here and in play.log, and each report as "worker done". The
hook gives the notes to the lead only: after its own shell commands and when a worker returns.
The conversation still grows over the hours, so when its context passes --fresh-at tokens (0:
never) the next round asks the player to bring NOTES.md and GOAL.md up to date, and the round
after starts a fresh conversation from them (the old ids are kept in claude-sessions.txt). The
rounds that ran on 500-800k tokens of context were slow and cost a few dollars each.

The lead plans ahead (Rory, 2026-10-22: "in the next run I don't want the lead waiting so much";
his longest wait is 5 minutes). A lead that has waited WAIT seconds while its workers run gets one
note saying so, with each worker's progress and, when the run has a staged plan (``fk stage``),
how far the plan reaches. <run>\\.loop\\workers.txt keeps each running worker's line current (its
minutes, tool calls and last command): the first lead run's lead could not see a long builder's
progress without reading its transcript.

2.0.7 (Rory, 2026-10-23: let the player restart itself at a good stopping point before its
conversation gets so long). The player hears when its context passes 150k tokens, and again every
100k after. When it creates <run>\\NEW-CONVERSATION and ends its turn, the next round starts a
fresh conversation from NOTES.md and GOAL.md, with the file's text, if any, as a note to itself. The
file is kept in .loop. A Stop hook that keeps the player going lets its stop through while the file
is there.

2.0.12 (the solo run, 2026-10-22 22:40 - 09:18: the loop died without a word and the game ran
10.6 hours unattended; then the base stood dead for hours while the world line spoke of ghosts
and research). The loop starts watchdog.py beside it, a process of its own that opens play.cmd
again when play.log has been silent 15 minutes with no loop running, and says so in play.log, in
the game chat and to the player. The world line leads with a dead base (no iron or copper plates
in the last minute), the reactor's fuel out or low and robots in chests while the network has
none, and ends with the plates per minute, the makers that stand and why, and items in chests
outside every logistic network; the first three are notes too, like no research.
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
FRESH_AT = 200000             # tokens of context: then a hand-over round and a fresh conversation
FRESH_MIN = 3                 # rounds a conversation runs at least before it is handed over
QUIET = 15                    # seconds the player is idle, nothing of its running: the round ends
GRACE = 60                    # minutes a round past --turn-cap runs on while its workers finish
WAIT = 300                    # seconds a lead waits on its workers before the loop says so (Rory)

#: to a lead whose round passed the cap while something of its still runs (2.0)
CAPPED = ("[From the loop] This round has run {cap:g} minutes, the loop's cap on a round. It ends "
          "when what runs now is done, and the next round starts from GOAL.md. A worker started "
          "from now on is stopped with the round at {hard} at the latest.")

#: to a lead that has waited WAIT seconds while its workers run (2.0, Rory 2026-10-22: the first
#: lead run's lead waited about 35 minutes on each of two builders, doing nothing else)
WAITED = ("[From the loop] You have waited {mins:g} minutes while your workers run, Rory's longest "
          "wait. {workers}Meanwhile you can design or check the next stage, adjust the plan to "
          "what the workers found, or measure something. {plan}")

#: the round that hands one conversation over to the next (2.0)
HANDOVER = ("[From the loop] This conversation has grown to about {k}k tokens of context, which "
            "makes every round slow and costly. The next round starts you a fresh conversation "
            "that begins from your files, so bring them up to date now: NOTES.md (what works, how "
            "the base is laid out and what for, what is planned, what to watch for) and GOAL.md "
            "(what's next, what's blocking, what to check first). Then end your turn.")
#: the player's own way to a fresh conversation (2.0.7, Rory 2026-10-23: the solo player's
#: conversation reached 466k tokens before Rory asked whether it wanted a fresh session; give it a
#: way to restart itself at a good stopping point): a file it creates in its folder, which the loop
#: takes at the next round and starts a fresh conversation from NOTES.md and GOAL.md
NEW = "NEW-CONVERSATION"
LONG_AT, LONG_EVERY = 150000, 100000  # tokens of context: the player hears so, then each 100k more
LONG = ("[From the loop] This conversation holds about {k}k tokens of context, which makes every "
        "step slower and costlier. At a good stopping point, with nothing half-built, bring "
        "NOTES.md and GOAL.md up to date, create an empty file named NEW-CONVERSATION in your "
        "folder and end your turn: the next turn starts a fresh conversation from them.")
#: the first message of the fresh conversation after a hand-over
FRESH = ("[From the loop] This is a fresh conversation: the one before grew long. AGENTS.md is "
         "your brief as before, and NOTES.md and GOAL.md are where you left off, brought up to "
         "date for this one. Read them, then carry on from where they leave off. GOAL.md says:")

#: one free read of the game: the ghosts per item (with the network's stock and whether the
#: recipe is locked), the ghosts outside every powered roboport's construction area (the 2005
#: player's silent deadlock: a re-laid grid left the poles that would join it out of reach), the
#: construction robots, the research, the labs that wait for packs and what their packs' makers
#: lack (2026-10-21: both players' research stood on one starved pack while the line said 11%),
#: the game chat after CURSOR, and (2.0.12) the base's health: iron and copper plates made in the
#: last minute, the reactors' fuel (what their feeding chests hold counts) and boilers without
#: fuel, the makers that stand and why, robots in chests, and items in chests outside every
#: logistic network. The solo run (2026-10-23 13:55-16:09): no coal, the reactor out of fuel and
#: nothing made, while the line spoke of ghosts and research; 5 logistic robots and 500 plastic
#: sat in chests for hours. The health read runs in a pcall: a mistake there never costs the rest
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
local ok, health = pcall(function()
  local ps, pm = f.get_item_production_statistics(s), defines.flow_precision_index.one_minute
  local plates = {}
  for _, n in pairs{"iron-plate", "copper-plate"} do
    plates[n] = {min = math.floor(ps.get_flow_count{name = n, category = "input",
                                                   precision_index = pm, count = false} + 0.5),
                 ever = ps.get_input_count(n)}
  end
  local function joules(inv)
    local j = 0
    for _, it in pairs(inv and inv.get_contents() or {}) do
      local p = prototypes.item[it.name]
      if p and p.fuel_value then j = j + p.fuel_value * it.count end
    end
    return j
  end
  local fuel = {}
  for _, e in pairs(s.find_entities_filtered{type = {"reactor", "boiler"}, force = f}) do
    local b = e.burner
    if b then
      local j = (b.remaining_burning_fuel or 0) + joules(b.inventory)
      if e.type == "reactor" then
        -- by the inserters' drop and pickup positions: drop_target stays nil on an inserter that
        -- has not moved yet (the laptop server, 2026-10-24)
        local p, bb, seen = e.position, e.bounding_box, {}
        for _, i in pairs(s.find_entities_filtered{type = "inserter", force = f,
            area = {{p.x - 5, p.y - 5}, {p.x + 5, p.y + 5}}}) do
          local d = i.drop_position
          if d.x >= bb.left_top.x and d.x <= bb.right_bottom.x and d.y >= bb.left_top.y
              and d.y <= bb.right_bottom.y then
            for _, c in pairs(s.find_entities_filtered{position = i.pickup_position, force = f,
                type = {"container", "logistic-container"}}) do
              if not seen[c.unit_number] then
                seen[c.unit_number] = true
                j = j + joules(c.get_inventory(defines.inventory.chest))
              end
            end
          end
        end
      end
      local t = fuel[e.type] or {n = 0, out = 0}
      t.n = t.n + 1
      if j <= 0 then
        t.out = t.out + 1
      else
        local use = e.prototype.get_max_energy_usage() or 0
        if use > 0 and (not t.min or j / use / 3600 < t.min) then t.min = j / use / 3600 end
      end
      fuel[e.type] = t
    end
  end
  local names = {}
  for k, v in pairs(defines.entity_status) do names[v] = k end
  local makers = {n = 0, stalled = {}}
  for _, a in pairs(s.find_entities_filtered{type = {"assembling-machine", "furnace"}, force = f}) do
    makers.n = makers.n + 1
    local st = a.status
    if st and st ~= defines.entity_status.working and st ~= defines.entity_status.normal then
      local k = names[st] or tostring(st)
      makers.stalled[k] = (makers.stalled[k] or 0) + 1
    end
  end
  local robots, off, piles = {construction = 0, logistic = 0}, {chests = 0, items = 0}, {}
  for _, c in pairs(s.find_entities_filtered{type = {"container", "logistic-container"}, force = f}) do
    local inv = c.get_inventory(defines.inventory.chest)
    if inv and not inv.is_empty() then
      local p = c.position
      for _, kind in pairs{"construction", "logistic"} do
        local n = inv.get_item_count(kind .. "-robot")
        if n > 0 then
          robots[kind] = robots[kind] + n
          robots.at = robots.at or {x = math.floor(p.x), y = math.floor(p.y)}
        end
      end
      local inside = (c.type == "logistic-container" and c.logistic_network)
                     or (c.type == "container" and s.find_logistic_network_by_position(p, f))
      if not inside then
        off.chests = off.chests + 1
        for _, it in pairs(inv.get_contents()) do
          off.items = off.items + it.count
          local q = piles[it.name] or {name = it.name, n = 0, most = 0}
          q.n = q.n + it.count
          if it.count > q.most then q.most, q.x, q.y = it.count, math.floor(p.x), math.floor(p.y) end
          piles[it.name] = q
        end
      end
    end
  end
  local top = {}
  for _, q in pairs(piles) do top[#top + 1] = q end
  table.sort(top, function(a, b) return a.n > b.n end)
  off.top = {top[1], top[2], top[3]}
  return {plates = plates, fuel = fuel, makers = makers, robots = robots, off = off}
end)
rcon.print(helpers.table_to_json{tick = game.tick, ghosts = ghosts, chat = chat,
  unreached = far > 0 and {n = far, first = at} or nil,
  robots = net and {idle = net.available_construction_robots, all = net.all_construction_robots,
                    logistic = net.all_logistic_robots},
  research = res and {name = res.name, pct = math.floor(f.research_progress * 100)},
  labs = labs, health = ok and health or {error = tostring(health)}})
"""


def claude_bin():
    """The newest claude.exe the desktop app keeps (looked up each round: the app updates it). The
    app is an MSIX package: outside it, its %APPDATA%\\Claude is under %LOCALAPPDATA%\\Packages.
    Since 2026-10-22 the app keeps it in %LOCALAPPDATA%\\Claude-Data\\claude_<package id> (the old
    folders were empty, and the loop logged "not signed in" hundreds of times a second)."""
    def version(p):
        return [int(x) if x.isdigit() else 0 for x in p.split(os.sep)[-3].split(".")]
    pats = [r"%LOCALAPPDATA%\Claude-Data\claude_*\claude-code\*\*\claude.exe",
            r"%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code\*\*\claude.exe",
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
    if name == "SubagentHandback":
        return "handback: " + short(inp.get("message", ""), 160)
    return f"{name} {short(json.dumps(inp), 160)}"


def context_of(usage):
    """The tokens one API call read: its new input and what came from the prompt cache."""
    u = usage or {}
    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                              "cache_creation_input_tokens"))


def _text(body):
    if isinstance(body, list):
        return " ".join(x.get("text", "") for x in body if isinstance(x, dict))
    return str(body or "")


def feed(ev, log, state):
    """One stream-json event: keep the session id and the results, show text and tool calls; the
    player's own context size, and each worker's report (2.0). A worker runs in the background
    (Claude Code 2.1.299: the Agent tool's result only says it was launched): its report comes
    in a ``task_notification`` event, and the lead gets it as a new message in the same process,
    so one turn of the loop can hold several of the player's turns, each with a ``result``."""
    if ev.get("session_id"):
        state["sid"] = ev["session_id"]
    pad = "    " if ev.get("parent_tool_use_id") else ""
    t = ev.get("type")
    agents = state.setdefault("agents", {})
    running = state.setdefault("running", set())
    if t == "system" and ev.get("subtype") == "task_started":
        running.add(ev.get("task_id"))
    theirs = state.setdefault("theirs", set())
    progress = state.setdefault("progress", {})
    if t == "system" and ev.get("subtype") == "task_notification":
        running.discard(ev.get("task_id"))
        if ev.get("tool_use_id") in theirs:
            # a worker's own background command: it wakes the worker, not the player, so the
            # player still waits and notes still reach it at once (the first lead run, 21:36-
            # 21:58 on 2026-10-21: each such task marked the waiting lead busy, and INBOX.md
            # sat in notes-pending.txt until the worker's report came)
            log(f"    background task {ev.get('status', 'done')}: "
                f"{short(ev.get('summary') or '', 200)}")
            return
        state["idle"] = False                      # its report wakes the player: a turn comes
        rep = (ev.get("handback_report") or {}).get("text") or ev.get("summary") or ""
        if ev.get("tool_use_id") not in agents:
            # a background shell command of the player's, not a worker (the first lead run's
            # log called one "worker completed" with nothing in it, 2026-10-21)
            log(f"{pad}background task {ev.get('status', 'done')}: {short(rep, 200)}")
            return
        what = agents.pop(ev.get("tool_use_id"))
        progress.pop(ev.get("tool_use_id"), None)
        use = ev.get("usage") or {}
        log(f"worker {ev.get('status', 'done')} ({short(what, 80)}; "
            f"{int(use.get('total_tokens') or 0) // 1000}k tokens, {use.get('tool_uses', 0)} tool "
            f"calls, {(use.get('duration_ms') or 0) / 60000:.0f} min): {short(rep, 800)}")
    elif t == "assistant":
        msg = ev.get("message", {})
        if not pad:
            state["idle"] = False                  # the player is on a turn
        if not pad and context_of(msg.get("usage")):
            state["context"] = context_of(msg.get("usage"))
        for c in msg.get("content", []):
            if c.get("type") == "text" and c.get("text", "").strip():
                log(pad + "> " + short(c["text"], 500))
            elif c.get("type") == "tool_use":
                state["tools"] += 1
                line = tool_line(c.get("name", "?"), c.get("input") or {})
                if pad:
                    theirs.add(c.get("id"))
                    # a worker's progress, for the lead without its transcript (2.0)
                    w = progress.setdefault(ev["parent_tool_use_id"], {"calls": 0})
                    w["calls"] += 1
                    w["last"] = line
                log(pad + line)
                if not pad and c.get("name") in ("Agent", "Task"):
                    agents[c.get("id")] = (c.get("input") or {}).get("description", "")
                    progress[c.get("id")] = {"calls": 0, "since": time.time()}
    elif t == "user":
        content = ev.get("message", {}).get("content", [])
        for c in content if isinstance(content, list) else []:
            if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                continue
            body = _text(c.get("content"))
            if not pad and c.get("tool_use_id") in agents and not c.get("is_error") \
                    and not body.startswith("Async agent launched"):
                # a worker the lead waited for (run_in_background false): its report is here
                what = agents.pop(c["tool_use_id"])
                state.setdefault("progress", {}).pop(c["tool_use_id"], None)
                log(f"worker done ({short(what, 80)}): " + short(body, 800))
            elif c.get("is_error"):
                log(pad + "  ! " + short(body, 200))
    elif t == "result":
        state["result"] = ev
        state["idle"] = True                       # its turn is over; workers may still run
        state["idle_at"] = time.time()
        if str(ev.get("result") or "").strip():
            state.setdefault("reports", []).append(ev["result"])


def workers_now(state, now=None):
    """One line per running worker: its task, minutes, tool calls and last command."""
    now = time.time() if now is None else now
    progress = state.get("progress") or {}
    lines = []
    for tid, what in (state.get("agents") or {}).items():
        w = progress.get(tid) or {}
        mins = f"{(now - w['since']) / 60:.0f} min, " if w.get("since") else ""
        lines.append(f"{short(what, 80) or 'a worker'}: {mins}{w.get('calls', 0)} tool calls"
                     + (f", last: {short(w['last'], 120)}" if w.get("last") else ""))
    return lines


def waited_note(state, plan=""):
    """WAITED, with the workers' progress and the plan's horizon (fk stage horizon)."""
    lines = workers_now(state)
    workers = ("Your workers now:\n" + "\n".join(f"- {ln}" for ln in lines) + "\n" if lines
               else "")
    plan = (plan[:1].upper() + plan[1:] if plan else "No staged plan yet: fk stage insert starts "
            "one (docs\\TOOLKIT.md, \"Planning ahead\").")
    return WAITED.format(mins=WAIT / 60, workers=workers, plan=plan)


def plan_horizon(folder):
    """``fk stage horizon`` through the run's own toolkit, or "" (no plan, or it failed). Pure: it
    reads the run's plan repository and computes rates on paper, no game call."""
    if not os.path.isdir(os.path.join(folder, ".stage")):
        return ""
    env = dict(os.environ, PYTHONPATH=os.path.join(folder, ".toolkit"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("FK_LINK", None)
    try:
        r = subprocess.run([sys.executable, "-m", "fkcore", "stage", ".", "horizon"],
                           cwd=os.path.join(folder, "game"), env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=90)
    except (OSError, subprocess.SubprocessError):
        r = None
    lines = (r.stdout or "").strip().splitlines() if r and r.returncode == 0 else []
    return lines[-1] if lines else "The plan's horizon could not be read now: fk stage list."


def user_message(text):
    """One line of Claude Code's streaming input (``--input-format stream-json``)."""
    return (json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"
            ).encode("utf-8")


def long_note(context, told):
    """LONG once each time the player's context passes LONG_AT, LONG_AT + LONG_EVERY, ...;
    ``told`` is [the last mark it heard], kept per conversation. -> the note, or ""."""
    if context < LONG_AT:
        return ""
    mark = LONG_AT + (context - LONG_AT) // LONG_EVERY * LONG_EVERY
    if mark <= told[0]:
        return ""
    told[0] = mark
    return LONG.format(k=context // 1000)


def pend(run, text):
    """A note for the player, as the watcher writes them: the hook hands it over after the
    player's next tool call, or the loop with its next message."""
    with open(os.path.join(run, ".loop", "notes-pending.txt"), "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n\n")


def new_conversation(run):
    """The player's NEW-CONVERSATION file, taken into .loop: its text ("" when empty), or None when
    there is none."""
    path = os.path.join(run, NEW)
    if not os.path.exists(path):
        return None
    kept = os.path.join(run, ".loop", f"{NEW.lower()}-{datetime.now():%Y%m%d-%H%M%S}.md")
    try:
        os.replace(path, kept)
    except OSError:
        return None                    # its writer still holds it: next round
    with open(kept, encoding="utf-8", errors="replace") as f:
        return f.read().strip()


def turn(run, sid, text, model, cap_min, log, events, take=None, horizon=None, heard=None,
         effort=None):
    """One claude -p round on the run's conversation -> (state, exit code, why it was cut short).

    2.0 (Rory, 2026-10-21: chat goes to the lead player at once): the round runs on streaming
    input. Its first message goes in as a user message and stdin stays open, so the player's
    workers run on in the background while it waits for them, and whatever ``take()`` returns
    (the watcher's notes: Rory's chat, INBOX.md, a build's hand edits) reaches a player that
    waits as a message of its own, at once; a busy player gets them from the hook after its next
    tool call. The round ends when the player is idle and nothing of its runs: stdin closes and
    the process exits. The first lead run (2026-10-21 21:05-21:09) showed both: Rory's chat sat
    in notes-pending.txt while the lead waited on a worker, and with stdin closed Claude Code
    ended the round 10 minutes after the lead's last turn, stopping that worker mid-build.

    A player that has waited WAIT seconds while something of its runs hears so once per wait,
    with ``horizon()`` (the plan's reach) in the note (2.0, Rory 2026-10-22: 5 minutes at most).
    With ``heard`` (2.0.7, the context marks heard in this conversation) the player hears when its
    context grows long (long_note)."""
    cmd = [claude_bin(), "-p", "--input-format", "stream-json", "--output-format", "stream-json",
           "--verbose", "--model", model, "--permission-mode", "auto", "--strict-mcp-config",
           "--settings", settings(run)]
    if effort:
        cmd += ["--effort", effort]    # 2.0.13 (Rory, 2026-10-24: a game with Opus at low effort)
    if sid:
        cmd += ["--resume", sid]
    state = {"sid": sid, "tools": 0, "result": None, "context": 0, "agents": {}, "reports": [],
             "idle": False, "running": set()}
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
    p.stdin.write(user_message(text))
    p.stdin.flush()
    # the cap (2.0, the first lead run: at 120 minutes the round was stopped with its workers
    # mid-task): past it the round ends at its next quiet moment, as any round does, and the lead
    # hears so once; only a round still busy GRACE minutes later is stopped, workers and all
    t0 = time.time()
    deadline, hard = t0 + cap_min * 60, t0 + (cap_min + GRACE) * 60
    cut, open_, capped, told = None, True, False, False
    waited, shown = None, None        # the wait the player heard about; workers.txt as written
    kept = sid                        # the conversation id in claude-session.txt
    while p.poll() is None:
        if state["sid"] and state["sid"] != kept:
            # kept at once (2.0.8): the id was written only when a round ended, so a first round
            # whose window was closed (2026-10-23 22:29, after an hour) lost its conversation
            kept = state["sid"]
            with open(os.path.join(run, "claude-session.txt"), "w") as f:
                f.write(kept)
        if os.path.exists(os.path.join(run, "STOP")):
            cut = "STOP"
        elif time.time() > hard:
            cut = "cap"
        if cut:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            p.wait()
            break
        if heard is not None:
            long = long_note(state["context"], heard)
            if long:
                pend(run, long)
                log(f"note: the conversation holds about {state['context'] // 1000}k tokens")
        if not capped and time.time() > deadline:
            capped = True
            log(f"round past its {cap_min:g}-minute cap: it ends when what runs now is done "
                f"({len(state['running'])} running), at {datetime.fromtimestamp(hard):%H:%M} "
                f"at the latest")
        if open_ and state["idle"]:
            notes = take() if take else ""
            if capped and not told and state["running"]:
                told = True
                cap = CAPPED.format(cap=cap_min, hard=f"{datetime.fromtimestamp(hard):%H:%M}")
                notes = cap + (f"\n\n{notes}" if notes else "")
            since = state.get("idle_at")
            if state["running"] and since and since != waited and time.time() - since > WAIT:
                # Rory's longest wait (2026-10-22): once per wait, a new one starts at its next turn
                waited = since
                wait = waited_note(state, horizon() if horizon else "")
                notes = wait + (f"\n\n{notes}" if notes else "")
            try:
                if notes:
                    # the player waits on its workers: it hears now, not at the next round
                    state["idle"] = False
                    p.stdin.write(user_message(notes))
                    p.stdin.flush()
                    log("handed to the player: " + short(notes, 300))
                elif not state["running"] and time.time() - state.get("idle_at", 0) > QUIET:
                    p.stdin.close()            # idle, nothing of its runs: the round ends
                    open_ = False
            except OSError:
                open_ = False                  # it exited meanwhile
        now = workers_now(state)
        if now != shown:
            shown = now
            _write_workers(run, now)
        time.sleep(2)
    th.join(timeout=10)
    err.close()
    return state, p.returncode, cut


def _write_workers(run, lines):
    """<run>\\.loop\\workers.txt: each running worker's line (the lead reads it when it likes)."""
    path = os.path.join(run, ".loop", "workers.txt")
    try:
        with open(path + ".new", "w", encoding="utf-8") as f:
            f.write(f"[Workers, {datetime.now():%H:%M}]\n"
                    + ("\n".join(lines) if lines else "no worker runs") + "\n")
        os.replace(path + ".new", path)
    except OSError:
        pass


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
        t0 = time.time()
        subprocess.run([claude_bin(), "auth", "login"], env=child_env(run))
        if time.time() - t0 < 10:
            time.sleep(60)             # a login that fails at once (no binary): don't spin
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


#: a maker's status (a defines.entity_status name) as the world line says it; others lose their _
STALLED = {"item_ingredient_shortage": "no ingredients", "fluid_ingredient_shortage": "no fluid",
           "no_input_fluid": "no fluid", "full_output": "output full",
           "waiting_for_space_in_destination": "output full", "no_power": "no power",
           "low_power": "low power", "no_fuel": "no fuel", "no_recipe": "no recipe",
           "disabled_by_control_behavior": "off by circuit",
           "marked_for_deconstruction": "to be taken up"}
FUEL_LOW = 30   # minutes of reactor fuel at full burn: less is LOW, and the player hears so

#: what blocks that is also a note, so it wakes a player that waits on its workers, once each time
#: it starts: no research (2.0) and, like it (2.0.12), a dead base and the reactor's fuel
WAKE = {"research:none": "[The labs stand idle: nothing researches. `fk research` queues the next "
                          "techs.]",
        "plates:none": "[The base is dead: no iron or copper plates in the last minute.]",
        "fuel:out": "[The reactor is out of fuel.]",
        "fuel:low": f"[The reactor's fuel is low: under {FUEL_LOW} minutes at full burn.]"}


def _dict(x):
    """Lua's empty table comes back as a JSON list."""
    return x if isinstance(x, dict) else {}


def health(st):
    """The base's health in the read (2.0.12) -> (alarms, which lead the world line; facts, which
    end it; the keys of what blocks: plates:none, fuel:out, fuel:low, robots:chest)."""
    h = _dict(st.get("health"))
    alarms, facts, blocked = [], [], []
    plates = _dict(h.get("plates"))
    if plates:
        fe, cu = _dict(plates.get("iron-plate")), _dict(plates.get("copper-plate"))
        made = fe.get("ever") or cu.get("ever")
        if not made:
            facts.append("no plates made yet")
        elif (fe.get("min") or 0) <= 0 and (cu.get("min") or 0) <= 0:
            alarms.append("BASE DEAD: no iron or copper plates made in the last minute")
            blocked.append("plates:none")
        else:
            facts.append(f"plates/min: iron {fe.get('min') or 0}, copper {cu.get('min') or 0}")
    fuel = _dict(h.get("fuel"))
    r = _dict(fuel.get("reactor"))
    if r.get("out"):
        alarms.append("REACTOR FUEL OUT" + (f" in {r['out']} of {r['n']} reactors"
                                            if r.get("n", 1) > 1 else ""))
        blocked.append("fuel:out")
    elif r.get("min") is not None and r["min"] < FUEL_LOW:
        alarms.append(f"REACTOR FUEL LOW: about {max(1, round(r['min']))} min left at full burn")
        blocked.append("fuel:low")
    b = _dict(fuel.get("boiler"))
    if b.get("out"):
        facts.append(f"{b['out']} of {b.get('n')} boilers without fuel")
    mk = _dict(h.get("makers"))
    why = {}
    for k, n in _dict(mk.get("stalled")).items():
        w = STALLED.get(k, k.replace("_", " "))
        why[w] = why.get(w, 0) + int(n)
    if why:
        facts.append(f"makers stalled {sum(why.values())} of {mk.get('n')}: " + ", ".join(
            f"{n} {w}" for w, n in sorted(why.items(), key=lambda kv: (-kv[1], kv[0]))[:5]))
    rb, net = _dict(h.get("robots")), st.get("robots") or {}
    inchest = [(rb[k], k) for k in ("logistic", "construction") if rb.get(k)]
    if inchest:
        at = _dict(rb.get("at"))
        text = (" and ".join(f"{n} {k} robots" for n, k in inchest) + " sit in chests, where they "
                f"do nothing (first at {at.get('x')},{at.get('y')})")
        if (rb.get("logistic") and not net.get("logistic")) or \
                (rb.get("construction") and not net.get("all")):
            alarms.append("ROBOTS IN CHESTS: " + text + ", while the network has none of them")
            blocked.append("robots:chest")
        else:
            facts.append(text)
    off = _dict(h.get("off"))
    if off.get("items"):
        top = [p for p in off.get("top") or [] if isinstance(p, dict)]
        facts.append(f"{off['items']} items sit in {off.get('chests')} chests outside every logistic "
                     "network" + (" (" + "; ".join(f"{p.get('n')} {p.get('name')}, most at "
                                                     f"{p.get('x')},{p.get('y')}" for p in top)
                                  + ")" if top else ""))
    return alarms, facts, blocked


def status_line(st):
    """-> (the world line, the key of what blocks: SHORT and needs-research ghost items, ghosts no
    powered roboport reaches, no research, research stalled with every lab waiting for packs,
    and (2.0.12) a dead base, the reactor's fuel out or low, robots in chests while the network
    has none). The base's alarms lead the line and its other health facts end it."""
    gh = sorted(st.get("ghosts") or [], key=lambda g: -g["ghosts"])
    total = sum(g["ghosts"] for g in gh)
    alarms, facts, blocked = health(st)
    parts = list(alarms)
    if total:
        items = []
        for g in gh[:8]:
            if g.get("stock"):
                why = f"{g['stock']} in the network"
            elif g.get("locked"):
                why = "needs-research: the network holds none and its recipe needs research"
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
    return "; ".join(parts + facts) + ".", ",".join(sorted(blocked))


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
        self.woke = set()                # the WAKE keys noted while they last
        self.health_error = None         # the health read's last error, logged once
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

    def take_notes(self):
        """The pending notes alone (Rory's chat, INBOX.md, a build's hand edits), for a player
        that waits on its workers (2.0): they wake it; the world line waits for its next tool
        call or round, so it doesn't wake the player every few minutes."""
        with self.mutex:
            return claude_hook.notes(self.dir)

    def hand(self):
        """New lines of game/out/hand.txt (what a build replaced or removed that someone placed
        by hand, 2.0) as a note for the player: it adopts each into the design, leaves it out,
        or comes back to it."""
        path = os.path.join(self.folder, "game", "out", "hand.txt")
        mark = os.path.join(self.dir, "hand-offset")
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        try:
            with open(mark) as f:
                seen = int(f.read().strip() or 0)
        except (OSError, ValueError):
            seen = 0
        if size <= seen:
            if size < seen:                    # a new file: read it from the start next time
                with open(mark, "w") as f:
                    f.write("0")
            return
        with open(path, "rb") as f:
            f.seek(seen)
            text = f.read().decode("utf-8", "replace").strip()
        with open(mark, "w") as f:
            f.write(str(size))
        if text:
            self.note("[A build replaced, removed or set back what someone did by hand]\n" + text +
                      "\n(Adopt it into the design, leave it out, or come back to it.)")
            self.log("hand: " + short(text, 300))

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
            # INBOX.md and INBOX-<anything>.md, one file per writer if they like; each is moved
            # before it is read, so a note written meanwhile lands in a new file (2026-10-21
            # 23:33: the supervisor's and the lead engineer's notes came within a minute and one
            # write replaced the other before the watcher read it)
            for inbox in sorted(glob.glob(os.path.join(self.folder, "INBOX*.md"))):
                name = os.path.basename(inbox)
                kept = os.path.join(self.dir, f"inbox-{datetime.now():%Y%m%d-%H%M%S}-{name}")
                try:
                    os.replace(inbox, kept)
                except OSError:
                    continue                   # its writer still holds it: next time
                with open(kept, encoding="utf-8") as f:
                    text = f.read().strip()
                if text:
                    self.note(f"[A message for you, from {name}]\n{text}")
                    self.log("inbox: " + short(text, 300))
            self.hand()
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
            err = _dict(st.get("health")).get("error")
            if err and err != self.health_error:
                self.log(f"  (watch: the health read failed: {short(err, 200)})")
            self.health_error = err
            # the world facts that are also notes (WAKE) wake a lead that waits on its workers,
            # once each time they start (2.0, the first lead run: the queue ran out while the lead
            # waited, 21:40-22:13 and 23:24-23:33 on 2026-10-21; 2.0.12, the solo run: the base
            # stood dead 13:55-16:09 on 2026-10-23 while the player watched research)
            now = {k for k in key.split(",") if k in WAKE}
            for k in sorted(now - self.woke):
                self.note(WAKE[k])
                self.log("note: " + WAKE[k].strip("[]"))
            self.woke = now
            since = time.time() - self.said
            due = (key != self.key and since > SETTLE) or (key and since > REMIND)
            if world or (due and (key or self.key)):
                self.world(line)
                self.log("world: " + line)
                self.said, self.key = time.time(), key


def settings(folder):
    """The --settings file: claude_hook.py after every tool call (2.0: any tool, so a busy
    player hears Rory's chat soon whatever it is doing; inside a worker the hook takes nothing),
    and wait_hook.py before every shell or Monitor command (2.0.11, Rory 2026-10-23: "dont wait"
    and wait commands are blocked)."""
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = f'python "{os.path.join(here, "claude_hook.py")}" "{folder}"'.replace("\\", "/")
    wait = f'python "{os.path.join(here, "wait_hook.py")}" "{folder}"'.replace("\\", "/")
    path = os.path.join(folder, ".loop", "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"hooks": {
            "PostToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": cmd, "timeout": 10}]}],
            "PreToolUse": [{"matcher": "Bash|PowerShell|Monitor", "hooks": [
                {"type": "command", "command": wait, "timeout": 10}]}]}}, f, indent=1)
    return path


def start_watchdog(run, log):
    """watchdog.py beside this file, as a process of its own (2.0.12): it opens play.cmd again when
    this loop dies. ``--detach`` starts it outside this process's tree and returns; a run's
    second watchdog ends at once, so each loop start may ask for one."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchdog.py")
    if not os.path.exists(path):
        return
    try:
        r = subprocess.run([sys.executable, path, run, "--detach"], capture_output=True,
                           text=True, timeout=30)
        if r.returncode:
            log(f"  (watchdog: exit {r.returncode}: {short(r.stderr, 200)})")
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"  (watchdog: {type(exc).__name__}: {short(exc, 200)})")


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
    ap.add_argument("--effort", default="", help="Claude Code's --effort (low, medium, high, ...)")
    ap.add_argument("--note", default="", help="a paragraph added to the first message")
    ap.add_argument("--fresh-at", type=int, default=FRESH_AT,
                    help="tokens of context after which a fresh conversation starts (0: never)")
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lock(run)
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: the laptop does not sleep while the loop plays
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    log = Log(run)
    start_watchdog(run, log)
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
    log(f"loop start: {run}, {a.model}{' at ' + a.effort + ' effort' if a.effort else ''}, conversation {sid or 'new'}; it stops on a STOP file, "
        f"{a.rounds} rounds or {a.hours:g} h, and pauses while GOAL.md is empty"
        + (f"; a fresh conversation after {a.fresh_at // 1000}k tokens of context"
           if a.fresh_at else ""))
    paused = False
    handing, fresh = False, False     # a hand-over round asked for, and the fresh start after it
    conv = 0                          # rounds done in this conversation (FRESH_MIN)
    told, asked_note = [0], ""         # the context marks heard in this conversation; NEW's text
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
        asked = new_conversation(run)
        if asked is not None:
            if sid:
                # the player asked for a fresh conversation at a stopping point of its own (2.0.7)
                with open(os.path.join(run, "claude-sessions.txt"), "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now():%Y-%m-%dT%H:%M:%S} {sid} asked\n")
                log(f"=== conversation {sid[:8]}: the player asked for a fresh one ({NEW}); this "
                    "round starts it from NOTES.md and GOAL.md")
                sid, handing, fresh, conv, restarted = "", False, True, 0, False
                told[0] = 0
                if os.path.exists(sid_file):
                    os.remove(sid_file)
                asked_note = asked
        if sid and handing:
            text = HANDOVER.format(k=handing // 1000)
        elif sid:
            text = (f"[GOAL.md, round {n + 1}. This message is the text of GOAL.md in your folder: "
                    f"edit that file to change what it says next time, or empty it to stop "
                    f"playing.]\n\n{goal}")
        elif fresh:
            text = f"{FRESH}\n\n{goal}" + (f"\n\n[Your note, from {NEW}]\n{asked_note}"
                                           if asked_note else "")
            fresh, asked_note = False, ""
        else:
            text = first
        if cut == "cap":
            text = (f"Your last round was stopped after {a.turn_cap + GRACE:g} minutes (the loop's "
                    f"cap on a round, with its grace for running workers), workers too. Carry on "
                    f"from where it was cut off.\n\n{text}")
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
        state, rc, cut = turn(run, sid, text, a.model, a.turn_cap, log, events, watch.take_notes,
                              lambda: plan_horizon(run), told, a.effort)
        if state["sid"] and state["sid"] != sid:
            sid = state["sid"]
            with open(sid_file, "w") as f:
                f.write(sid)
        res, mins = state["result"] or {}, (time.time() - t0) / 60
        if handing and (cut or (res and not res.get("is_error"))):
            # the hand-over round is over: the next one starts a fresh conversation
            for text in state["reports"]:
                log("turn report: " + short(text, 1500))
            with open(os.path.join(run, "claude-sessions.txt"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%dT%H:%M:%S} {sid} {handing}\n")
            log(f"=== conversation {sid[:8]} handed over at about {handing // 1000}k tokens; "
                "the next round starts a fresh one from NOTES.md and GOAL.md")
            sid, handing, fresh, conv = "", False, True, 0
            told[0] = 0
            if os.path.exists(sid_file):
                os.remove(sid_file)
            if cut != "STOP":
                cut = None
                continue
        if cut:
            log(f"=== round {n} cut short ({cut}) after {mins:.0f} min, {state['tools']} tool calls")
            fails = 0
            continue
        if res and not res.get("is_error"):
            fails = 0
            log(f"=== round {n} done: {mins:.1f} min, {res.get('num_turns')} steps, "
                f"{state['tools']} tool calls, ${res.get('total_cost_usd') or 0:.2f}, "
                f"context {state['context'] // 1000}k tokens")
            for text in state["reports"]:
                log("turn report: " + short(text, 1500))
            conv += 1
            if a.fresh_at and state["context"] >= a.fresh_at and conv >= FRESH_MIN:
                handing = state["context"]
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
