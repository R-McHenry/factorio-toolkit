"""2.0 (Rory, 2026-10-21): a Claude lead player with Claude worker subagents. The run setup
(kickoff/new_run.py --workers claude), the hook that keeps Rory's notes for the lead, the loop's
log of each worker's report and of the lead's context, and one fk build at a time. Offline: no
claude, no game."""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "kickoff"))
sys.path.insert(0, os.path.join(ROOT, "agent"))
import claude_hook  # noqa: E402
import claude_loop  # noqa: E402
import fk  # noqa: E402  (agent/fk.py, the player's command)
import new_run  # noqa: E402


def tree_archive(_sha, dest, paths=("fkcore",)):
    """new_run._archive from the working tree instead of a commit."""
    for p in paths:
        src, out = os.path.join(ROOT, p), os.path.join(dest, p)
        if os.path.isdir(src):
            shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__", "out"))
        else:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy(src, out)


class RunSetupTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkworkers-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.run_dir = os.path.join(self.dir, "run")

    def make(self, **kw):
        with mock.patch.object(new_run, "_archive", tree_archive):
            return new_run.make(self.run_dir, **kw)

    def read(self, *parts):
        with open(os.path.join(self.run_dir, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_a_lead_run_gets_the_worker_agent(self):
        cfg = self.make(prompt="lead-v1", player="claude", workers="claude", local={})
        worker = self.read(".claude", "agents", "worker.md")
        head, body = worker.split("\n---\n\n", 1)
        self.assertIn("name: worker\n", head)
        self.assertIn("model: inherit\n", head)
        self.assertIn("disallowedTools: Agent\n", head)
        self.assertIn("omitClaudeMd: true", head)
        with open(os.path.join(ROOT, "agent", "prompts", "worker-v1.md"), encoding="utf-8") as fh:
            self.assertEqual(body, fh.read())
        self.assertEqual(cfg["workers"]["backend"], "claude")
        self.assertEqual(json.loads(self.read("run.json"))["workers"]["model"], "inherit")
        self.assertIn("You lead it.", self.read("AGENTS.md"))
        self.assertTrue(json.loads(self.read("launch.json"))["first"].startswith(
            "Lead the Factorio run"))
        self.assertTrue(os.path.isdir(os.path.join(self.run_dir, "reports")))
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "play.cmd")))

    def test_the_workers_model_can_be_named(self):
        self.make(prompt="lead-v1", player="claude", workers="claude", worker_model="sonnet",
                  local={})
        self.assertIn("model: sonnet\n", self.read(".claude", "agents", "worker.md"))

    def test_a_run_without_workers_is_as_before(self):
        cfg = self.make(player="claude", local={})
        self.assertNotIn("workers", cfg)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, ".claude")))
        self.assertTrue(json.loads(self.read("launch.json"))["first"].startswith("Play Factorio"))

    def test_workers_need_a_claude_player(self):
        with self.assertRaises(SystemExit):
            self.make(prompt="lead-v1", player="deepseek", workers="claude", local={})

    def test_the_command_line_picks_the_lead_brief(self):
        seen = {}
        with mock.patch.object(new_run, "make", lambda *a: seen.setdefault("a", a) and {}):
            with mock.patch("sys.stdout", io.StringIO()):
                new_run.main([self.run_dir, "--player", "claude", "--workers", "claude"])
        run, prompt = seen["a"][:2]
        self.assertEqual((prompt, seen["a"][-2], seen["a"][-1]), ("lead-v1", "claude", "inherit"))


class HookTest(unittest.TestCase):
    """The notes (Rory's chat, INBOX.md, the world line) are the lead's: a tool call inside a
    worker takes nothing, and the lead gets them at its next shell command or when the worker
    returns (the Agent tool runs the hook too)."""

    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fkhook-")
        self.addCleanup(shutil.rmtree, self.run, True)
        os.makedirs(os.path.join(self.run, ".loop"))
        with open(os.path.join(self.run, ".loop", "notes-pending.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("[Rory_618 in game chat] more red science, please\n\n")

    def hook(self, payload):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                mock.patch("sys.stdout", out), \
                mock.patch("sys.argv", ["claude_hook.py", self.run]):
            claude_hook.main()
        return out.getvalue()

    def test_a_workers_tool_call_leaves_the_notes_for_the_lead(self):
        said = self.hook({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                          "agent_id": "a1b2", "agent_type": "worker"})
        self.assertEqual(said, "")
        self.assertTrue(os.path.exists(os.path.join(self.run, ".loop", "notes-pending.txt")))
        said = self.hook({"hook_event_name": "PostToolUse", "tool_name": "Agent"})
        self.assertIn("more red science, please",
                      json.loads(said)["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(os.path.exists(os.path.join(self.run, ".loop", "notes-pending.txt")))

    def test_the_hook_runs_after_every_tool_of_the_lead(self):
        path = claude_loop.settings(self.run)
        with open(path, encoding="utf-8") as fh:
            matcher = json.load(fh)["hooks"]["PostToolUse"][0]["matcher"]
        self.assertEqual(matcher, "*")

    def test_wait_commands_are_blocked(self):
        # Rory (2026-10-23): "dont wait" and wait commands are blocked
        path = claude_loop.settings(self.run)
        with open(path, encoding="utf-8") as fh:
            pre = json.load(fh)["hooks"]["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "Bash|PowerShell|Monitor")
        self.assertIn("wait_hook.py", pre["hooks"][0]["command"])
        import wait_hook
        for cmd, blocked in (("sleep 5; ls", True), ("timeout 590 bash -c 'until x; do sleep 10; done'", True),
                             ("python bin/fk.py wait built 1,1,9,9 --max 2m", True),
                             ("Start-Sleep -Seconds 30", True), ("python bin/fk.py build", False),
                             ("grep -n sleep NOTES.md", False)):
            raw = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(raw)), mock.patch("sys.stdout", out), \
                    mock.patch("sys.argv", ["wait_hook.py", self.run]):
                wait_hook.main()
            if blocked:
                decision = json.loads(out.getvalue())["hookSpecificOutput"]
                self.assertEqual((decision["permissionDecision"], decision["permissionDecisionReason"]),
                                 ("deny", "Don't wait."), cmd)
            else:
                self.assertEqual(out.getvalue(), "", cmd)


class WatchTest(unittest.TestCase):
    """2.0: what the watcher hands a lead that waits on its workers: notes only (chat, INBOX.md,
    a build's hand edits), never the world line; and out/hand.txt's new lines as a note."""

    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fkwatch-")
        self.addCleanup(shutil.rmtree, self.run, True)
        os.makedirs(os.path.join(self.run, "game", "out"))
        with open(os.path.join(self.run, "run.json"), "w") as fh:
            fh.write("{}")
        self.watch = claude_loop.Watch(self.run, lambda _text: None)

    def test_hand_edits_become_a_note_once(self):
        hand = os.path.join(self.run, "game", "out", "hand.txt")
        with open(hand, "w", encoding="utf-8") as fh:
            fh.write("# 2026-10-21 21:05 fk build: 1 placed by hand\n  Rory_618 placed long-handed-"
                     "inserter at 78.5,46 on coal/~cfuel/s0's tile; this build replaces it\n")
        self.watch.check()
        notes = self.watch.take_notes()
        self.assertIn("[A build replaced or removed what someone placed by hand]", notes)
        self.assertIn("on coal/~cfuel/s0's tile; this build replaces it", notes)
        self.watch.check()
        self.assertEqual(self.watch.take_notes(), "")             # each line once
        with open(hand, "a", encoding="utf-8") as fh:
            fh.write("# 21:30 fk build: 1 placed by hand\n  Rory_618 placed pipe at 1.5,2.5 on x's "
                     "tile; this build replaces it\n")
        self.watch.check()
        notes = self.watch.take_notes()
        self.assertIn("pipe at 1.5,2.5", notes)
        self.assertNotIn("78.5,46", notes)

    def test_every_inbox_file_is_a_note_once(self):
        # 2026-10-21 23:33: two writers within a minute, and one INBOX.md replaced the other
        for name, text in (("INBOX.md", "from the lead engineer"),
                           ("INBOX-supervisor.md", "from the supervisor")):
            with open(os.path.join(self.run, name), "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        self.watch.check()
        notes = self.watch.take_notes()
        self.assertIn("[A message for you, from INBOX.md]\nfrom the lead engineer", notes)
        self.assertIn("[A message for you, from INBOX-supervisor.md]\nfrom the supervisor", notes)
        self.assertFalse([n for n in os.listdir(self.run) if n.startswith("INBOX")])
        self.watch.check()
        self.assertEqual(self.watch.take_notes(), "")

    def test_no_research_is_a_note_once_each_time(self):
        # the first lead run (2026-10-21): the queue ran out twice while the lead waited
        status = {"ghosts": [], "research": None}
        self.watch.cfg = {"host": "computah-ct"}
        with mock.patch.object(claude_loop, "host_status", lambda *a: dict(status)):
            self.watch.check()
            self.assertIn("[The labs stand idle: nothing researches.", self.watch.take_notes())
            self.watch.check()
            self.assertEqual(self.watch.take_notes(), "")         # once while it lasts
            status["research"] = {"name": "concrete", "pct": 4}
            self.watch.check()
            status["research"] = None
            self.watch.check()
            self.assertIn("nothing researches", self.watch.take_notes())   # again, a new gap

    def test_a_waiting_lead_gets_notes_not_the_world_line(self):
        self.watch.world("no ghosts wait")
        self.watch.note("[Rory_618 in game chat] hi")
        self.assertEqual(self.watch.take_notes(), "[Rory_618 in game chat] hi")
        self.assertIn("no ghosts wait", self.watch.take())          # the next round's message


class StreamTest(unittest.TestCase):
    """2.0: the round's process keeps its input open; the loop knows when the player waits and
    whether anything of its still runs."""

    def test_idle_and_running(self):
        state = {"sid": "", "tools": 0, "result": None, "context": 0, "agents": {}}
        log = [].append
        claude_loop.feed({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "w"}}]}},
            log, state)
        claude_loop.feed({"type": "system", "subtype": "task_started", "task_id": "a1",
                          "tool_use_id": "t1"}, log, state)
        claude_loop.feed({"type": "result", "result": "waiting"}, log, state)
        self.assertTrue(state["idle"])
        self.assertEqual(state["running"], {"a1"})                # keep the input open
        claude_loop.feed({"type": "system", "subtype": "task_notification", "task_id": "a1",
                          "tool_use_id": "t1", "status": "completed"}, log, state)
        self.assertEqual(state["running"], set())
        self.assertFalse(state["idle"])                           # its report wakes the player
        claude_loop.feed({"type": "result", "result": "done"}, log, state)
        self.assertTrue(state["idle"])

    def test_a_workers_own_background_command_leaves_the_player_waiting(self):
        # the first lead run (2026-10-21 21:36-21:58): a worker's background Bash finished,
        # the loop took the waiting lead for busy, and INBOX.md waited for the worker's report
        lines, state = [], {"sid": "", "tools": 0, "result": None, "context": 0, "agents": {}}
        log = lines.append
        claude_loop.feed({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "w"}}]}},
            log, state)
        claude_loop.feed({"type": "result", "result": "waiting"}, log, state)
        claude_loop.feed({"type": "assistant", "parent_tool_use_id": "t1", "message": {
            "content": [{"type": "tool_use", "id": "w1", "name": "Bash",
                         "input": {"command": "sleep 30", "run_in_background": True}}]}},
            log, state)
        claude_loop.feed({"type": "system", "subtype": "task_started", "task_id": "b1",
                          "tool_use_id": "w1"}, log, state)
        claude_loop.feed({"type": "system", "subtype": "task_notification", "task_id": "b1",
                          "tool_use_id": "w1", "status": "completed",
                          "summary": "Poll belts to 200"}, log, state)
        self.assertTrue(state["idle"])                            # notes still go in at once
        self.assertEqual(lines[-1], "    background task completed: Poll belts to 200")
        self.assertEqual(state["agents"], {"t1": "w"})            # the worker still runs

    def run_round(self, script, cap_min=1, horizon=None, told=None):
        """turn() on a fake claude process and a fake clock: ``script`` is [(at seconds, event)],
        each event sent once the clock reaches it. -> (state, cut, the messages written in, log,
        the commands run, the clock at the end)."""
        clock, real_sleep, written, lines, ran = [0.0], time.sleep, [], [], []

        class Proc:
            pid, returncode = 4242, None

            def __init__(self, *a, **kw):
                self.closed, self.stdin = False, self
                self.stdout = self.out()

            def write(self, raw):
                written.append(json.loads(raw.decode("utf-8"))["message"]["content"])

            def flush(self):
                pass

            def close(self):
                self.closed = True

            def out(self):
                for at, ev in script:
                    while clock[0] < at and not self.closed:
                        real_sleep(0.002)
                    if self.closed:
                        return
                    yield (json.dumps(ev) + "\n").encode("utf-8")

            def poll(self):
                return 0 if self.closed else None

            def wait(self):
                self.closed = True

        class Clock:
            @staticmethod
            def time():
                return 1_700_000_000 + clock[0]

            @staticmethod
            def sleep(s):
                clock[0] += s
                real_sleep(0.004)

        def run(cmd, **kw):
            ran.append(cmd)
            if cmd[0] == "taskkill":
                procs[0].closed = True

        procs = []
        d = tempfile.mkdtemp(prefix="fkcap-")
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, ".loop"))
        self.run_dir = d
        with mock.patch.object(claude_loop, "time", Clock), \
                mock.patch.object(claude_loop, "claude_bin", lambda: "claude"), \
                mock.patch.object(claude_loop.subprocess, "Popen",
                                  lambda *a, **kw: procs.append(Proc()) or procs[0]), \
                mock.patch.object(claude_loop.subprocess, "run", run):
            state, rc, cut = claude_loop.turn(d, "sid", "go", "m", cap_min, lines.append,
                                              io.StringIO(), take=lambda: "", horizon=horizon,
                                              heard=told)
        with open(os.path.join(d, ".loop", "workers.txt"), encoding="utf-8") as fh:
            self.workers_txt = fh.read()
        return state, cut, written, lines, ran, clock[0]

    LAUNCH = [(0, {"type": "assistant", "message": {"content": [
                  {"type": "tool_use", "id": "t1", "name": "Agent",
                   "input": {"description": "build the labs"}}]}}),
              (0, {"type": "system", "subtype": "task_started", "task_id": "a1",
                   "tool_use_id": "t1"}),
              (1, {"type": "result", "result": "waiting for the labs"})]

    def test_past_the_cap_a_round_waits_for_its_workers(self):
        # the first lead run (2026-10-21): at 120 minutes the round was stopped, workers and all
        script = self.LAUNCH + [
            (70, {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}),
            (71, {"type": "result", "result": "ok, waiting"}),
            (100, {"type": "system", "subtype": "task_notification", "task_id": "a1",
                   "tool_use_id": "t1", "status": "completed", "summary": "labs stand"}),
            (101, {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}),
            (102, {"type": "result", "result": "done"})]
        state, cut, written, lines, ran, end = self.run_round(script)
        self.assertIsNone(cut)                                        # no stop: it ended quietly
        self.assertFalse([c for c in ran if c[0] == "taskkill"])
        self.assertEqual(written[0], "go")
        self.assertEqual(len(written), 2)                             # the cap note, once
        self.assertTrue(written[1].startswith("[From the loop] This round has run 1 minutes"))
        self.assertTrue([l for l in lines if l.startswith("round past its 1-minute cap")])
        self.assertTrue(102 < end < 102 + claude_loop.QUIET + 10)    # ended at the quiet moment

    def test_a_round_still_busy_after_the_grace_is_stopped(self):
        state, cut, written, lines, ran, end = self.run_round(list(self.LAUNCH))
        self.assertEqual(cut, "cap")
        self.assertTrue([c for c in ran if c[0] == "taskkill"])
        self.assertGreater(end, (1 + claude_loop.GRACE) * 60)

    def test_a_lead_that_waits_five_minutes_hears_so_once_per_wait(self):
        # Rory (2026-10-22): the first lead run's lead waited about 35 minutes on each of two
        # builders; his longest wait is 5 minutes
        script = self.LAUNCH + [
            (40, {"type": "assistant", "parent_tool_use_id": "t1", "message": {"content": [
                {"type": "tool_use", "id": "w1", "name": "Bash",
                 "input": {"command": "fk build"}}]}}),
            (320, {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}),
            (321, {"type": "result", "result": "designed stage 4"}),
            (500, {"type": "system", "subtype": "task_notification", "task_id": "a1",
                   "tool_use_id": "t1", "status": "completed", "summary": "labs stand"}),
            (501, {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}),
            (502, {"type": "result", "result": "done"})]
        state, cut, written, lines, ran, end = self.run_round(
            script, cap_min=120, horizon=lambda: "the plan: 2 stages ahead; horizon 1.20x")
        self.assertIsNone(cut)
        self.assertEqual(len(written), 2)                  # one note: the second wait was short
        note = written[1]
        self.assertTrue(note.startswith("[From the loop] You have waited 5 minutes while your "
                                        "workers run, Rory's longest wait."), note)
        self.assertIn("- build the labs: 5 min, 1 tool calls, last: $ fk build", note)
        self.assertTrue(note.endswith("The plan: 2 stages ahead; horizon 1.20x"), note)
        self.assertEqual(self.workers_txt.splitlines()[1:], ["no worker runs"])

    def test_the_wait_note_without_a_plan_points_to_fk_stage(self):
        note = claude_loop.waited_note({"agents": {}})
        self.assertIn("No staged plan yet: fk stage insert starts one", note)
        self.assertNotIn("Your workers now", note)
        self.assertEqual(claude_loop.plan_horizon(tempfile.gettempdir()), "")   # no .stage

    def test_the_workers_line_while_one_runs(self):
        state = {"agents": {"t1": "build the red block"},
                 "progress": {"t1": {"calls": 12, "since": 1000.0, "last": "$ fk look 0,0,9,9"}}}
        self.assertEqual(claude_loop.workers_now(state, now=1000.0 + 34 * 60),
                         ["build the red block: 34 min, 12 tool calls, last: $ fk look 0,0,9,9"])

    def test_past_the_cap_with_nothing_running_the_round_just_ends(self):
        script = [(0, {"type": "assistant", "message": {"content": [{"type": "text", "text": "hm"}]}}),
                  (90, {"type": "result", "result": "done"})]
        state, cut, written, lines, ran, end = self.run_round(script)
        self.assertIsNone(cut)
        self.assertEqual(written, ["go"])                             # no note: nothing runs

    def test_a_long_conversation_hears_so_once_per_100k(self):
        # Rory (2026-10-23): let the player restart itself at a good stopping point before its
        # conversation gets so long (the solo player's reached 466k)
        def call(k):
            return {"type": "assistant", "message": {"usage": {"cache_read_input_tokens": k * 1000},
                                                     "content": [{"type": "text", "text": "."}]}}
        script = [(0, call(120)), (10, call(160)), (20, call(190)), (30, call(260)),
                  (40, {"type": "result", "result": "done"})]
        told = [0]
        state, cut, written, lines, ran, end = self.run_round(script, cap_min=120, told=told)
        with open(os.path.join(self.run_dir, ".loop", "notes-pending.txt"), encoding="utf-8") as fh:
            notes = [n for n in fh.read().split("\n\n") if n.strip()]
        self.assertEqual(len(notes), 2)                       # at 160k and at 260k, not at 190k
        self.assertTrue(notes[0].startswith("[From the loop] This conversation holds about 160k"))
        self.assertIn("create an empty file named NEW-CONVERSATION", notes[0])
        self.assertIn("about 260k", notes[1])
        self.assertEqual(told, [250000])
        self.assertEqual(claude_loop.long_note(255000, told), "")   # heard already
        self.assertEqual(claude_loop.long_note(140000, [0]), "")    # below the first mark

    def test_a_new_conversations_id_is_kept_at_once(self):
        # 2026-10-23 22:29: a first round's window was closed after an hour, and the id, written
        # only when the round ended, was lost with the conversation
        script = [(0, {"type": "system", "subtype": "init", "session_id": "c0ffee"}),
                  (5, {"type": "assistant", "message": {"content": [{"type": "text", "text": "."}]}}),
                  (6, {"type": "result", "result": "done"})]
        self.run_round(script, cap_min=120)
        with open(os.path.join(self.run_dir, "claude-session.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "c0ffee")

    def test_the_new_conversation_file_is_taken_once(self):
        d = tempfile.mkdtemp(prefix="fknew-")
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, ".loop"))
        self.assertIsNone(claude_loop.new_conversation(d))
        with open(os.path.join(d, claude_loop.NEW), "w", encoding="utf-8") as fh:
            fh.write("Mall3 pasted; check its belts first.\n")
        self.assertEqual(claude_loop.new_conversation(d), "Mall3 pasted; check its belts first.")
        self.assertFalse(os.path.exists(os.path.join(d, claude_loop.NEW)))
        self.assertEqual(len([f for f in os.listdir(os.path.join(d, ".loop"))
                              if f.startswith("new-conversation-")]), 1)
        self.assertIsNone(claude_loop.new_conversation(d))

    def test_a_streaming_message(self):
        self.assertEqual(json.loads(claude_loop.user_message("hi").decode("utf-8")),
                         {"type": "user", "message": {"role": "user", "content": "hi"}})


class LoopFeedTest(unittest.TestCase):
    """play.log shows each worker's report, and the loop knows the lead's own context size (a
    worker's API calls read their own context, not the lead's)."""

    def test_a_workers_report_and_the_leads_context(self):
        lines, state = [], {"sid": "", "tools": 0, "result": None, "context": 0, "agents": {}}
        log = lines.append
        claude_loop.feed({"type": "assistant", "message": {
            "usage": {"input_tokens": 12, "cache_read_input_tokens": 40000,
                      "cache_creation_input_tokens": 2000},
            "content": [{"type": "tool_use", "id": "t1", "name": "Agent",
                         "input": {"description": "build the iron array",
                                   "subagent_type": "worker", "prompt": "..."}}]}}, log, state)
        self.assertEqual(state["context"], 42012)
        claude_loop.feed({"type": "assistant", "parent_tool_use_id": "t1", "message": {
            "usage": {"input_tokens": 5, "cache_read_input_tokens": 90000},
            "content": [{"type": "tool_use", "id": "w1", "name": "Bash",
                         "input": {"command": "python bin/fk.py build"}}]}}, log, state)
        self.assertEqual(state["context"], 42012)                   # the worker's, not counted
        self.assertIn("    $ python bin/fk.py build", lines)
        claude_loop.feed({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": [{"type": "text", "text": "Built: 32 furnaces stand; 4 ghosts wait for "
                                                  "inserters (SHORT)."}]}]}}, log, state)
        self.assertEqual(lines[-1], "worker done (build the iron array): Built: 32 furnaces "
                                    "stand; 4 ghosts wait for inserters (SHORT).")
        self.assertEqual(state["agents"], {})

    def test_a_worker_in_the_background_reports_by_notification(self):
        # Claude Code 2.1.299, measured with claude -p: the Agent tool returns at once ("Async
        # agent launched"); the report comes in a task_notification, and the lead's next turn in
        # the same process ends in a result of its own
        lines, state = [], {"sid": "", "tools": 0, "result": None, "context": 0, "agents": {}}
        log = lines.append
        claude_loop.feed({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Agent",
             "input": {"description": "scout the copper patch", "subagent_type": "worker"}}]}},
            log, state)
        claude_loop.feed({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": [
                {"type": "text", "text": "Async agent launched successfully. agentId: a1"}]}]}},
            log, state)
        self.assertFalse([l for l in lines if l.startswith("worker")])
        claude_loop.feed({"type": "result", "result": "Waiting for the scout.",
                          "is_error": False}, log, state)
        claude_loop.feed({"type": "system", "subtype": "task_notification", "tool_use_id": "t1",
                          "status": "completed", "usage": {"total_tokens": 15157,
                                                            "tool_uses": 2,
                                                            "duration_ms": 240000},
                          "handback_report": {"text": "Copper at 120,-40, 2.1M ore."}},
                         log, state)
        self.assertEqual(lines[-1], "worker completed (scout the copper patch; 15k tokens, 2 tool "
                                    "calls, 4 min): Copper at 120,-40, 2.1M ore.")
        claude_loop.feed({"type": "result", "result": "Copper next: plot copper at 110,-50.",
                          "is_error": False}, log, state)
        claude_loop.feed({"type": "result", "result": "", "is_error": False}, log, state)
        self.assertEqual(state["reports"], ["Waiting for the scout.",
                                            "Copper next: plot copper at 110,-50."])

    def test_a_background_shell_task_is_no_worker(self):
        # the first lead run (2026-10-21 20:40): the lead's background command came back as a
        # task_notification with no Agent call behind it
        lines, state = [], {"sid": "", "tools": 0, "result": None, "context": 0, "agents": {}}
        claude_loop.feed({"type": "system", "subtype": "task_notification", "tool_use_id": "b1",
                          "status": "completed", "summary": "Check research and kit stock"},
                         lines.append, state)
        self.assertEqual(lines, ["background task completed: Check research and kit stock"])

    def test_the_hand_over_and_fresh_messages_name_the_files(self):
        self.assertIn("NOTES.md", claude_loop.HANDOVER)
        self.assertIn("GOAL.md", claude_loop.HANDOVER)
        self.assertIn("about 250k tokens", claude_loop.HANDOVER.format(k=250))
        self.assertIn("AGENTS.md is your brief as before", claude_loop.FRESH)


class BuildLockTest(unittest.TestCase):
    """Two workers that build at once would paste over each other's design: a second fk build
    waits for the first."""

    def test_a_second_build_waits_for_the_first(self):
        d = tempfile.mkdtemp(prefix="fklock-")
        self.addCleanup(shutil.rmtree, d, True)
        done = []
        with mock.patch.object(fk, "RUN", d), mock.patch("sys.stdout", io.StringIO()) as out:
            with fk._build_lock():
                t = threading.Thread(target=lambda: fk._build_lock().__enter__()
                                     or done.append(1), daemon=True)
                t.start()
                time.sleep(1.0)
                self.assertEqual(done, [])                          # still waiting
            t.join(timeout=10)
            self.assertEqual(done, [1])
            self.assertIn("another build runs in this run", out.getvalue())


if __name__ == "__main__":
    unittest.main()
