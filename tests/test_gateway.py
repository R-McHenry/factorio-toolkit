"""3.4 (PLAN-COMMONS step 2): the fk-gateway against a fake RCON server, driven by the toolkit's
own client (link.Relay, fkcore.commons)."""
import json
import os
import socket
import socketserver
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

from fkcore import commons, gateway, link


class FakeGame(socketserver.ThreadingTCPServer):
    """Source RCON, enough for link.Rcon: auth, then every command to ``answer``."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Rcon)
        self.cmds, self.hang, self.script_output = [], False, None
        self.players, self.paused, self.saves = 0, False, None

    def answer(self, cmd):
        self.cmds.append(cmd)
        if "game.tick .." in cmd:
            return f"1000 {self.players} {'true' if self.paused else 'false'}"
        if "game.tick_paused = " in cmd:
            self.paused = "= true" in cmd
        if "server_save('gateway')" in cmd and self.saves:
            with open(os.path.join(self.saves, "gateway.tmp.zip"), "wb") as fh:
                fh.write(b"as it stands")
            os.replace(os.path.join(self.saves, "gateway.tmp.zip"),
                       os.path.join(self.saves, "gateway.zip"))
        if "write_file" in cmd:                          # write_file('PATH', 'TEXT') as the game does
            path, text = cmd.split("write_file('", 1)[1].split("')", 1)[0].split("', '")
            full = os.path.join(self.script_output, *path.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(text)
            return "1"
        return "ok"


class _Rcon(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            head = self.request.recv(4)
            if len(head) < 4:
                return
            (n,) = struct.unpack("<i", head)
            data = b""
            while len(data) < n:
                data += self.request.recv(n - len(data))
            rid, typ = struct.unpack("<ii", data[:8])
            body = data[8:-2].decode()
            if typ == 3:
                reply, rtyp = "", 2
            else:
                if self.server.hang:
                    time.sleep(30)
                    return
                reply, rtyp = self.server.answer(body), 0
            out = struct.pack("<ii", rid, rtyp) + reply.encode() + b"\x00\x00"
            self.request.sendall(struct.pack("<i", len(out)) + out)


class GatewayCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.game = FakeGame()
        threading.Thread(target=self.game.serve_forever, args=(0.02,), daemon=True).start()
        self.out = self.game.script_output = os.path.join(t, "script-output")
        self.saves = os.path.join(t, "saves")
        self.docs = os.path.join(t, "docs")
        for d in (self.out, self.saves, self.docs):
            os.makedirs(d)
        with open(os.path.join(t, "rcon.pw"), "w") as fh:
            fh.write("pw")
        with open(os.path.join(self.docs, "skill.md"), "wb") as fh:
            fh.write(b"# come and play\n")
        self.flag = os.path.join(t, "restarted")
        self.cfg = {
            "listen": ["127.0.0.1", 0], "data": os.path.join(t, "data"), "docs": self.docs,
            "rcon_timeout": 2.0,
            "watchdog": {"every_s": 3600, "fails": 2, "cooldown_s": 0},
            "saves": {"t": {"rcon_port": self.game.server_address[1],
                            "pw_file": os.path.join(t, "rcon.pw"), "script_output": self.out,
                            "saves": self.saves, "factorio": "2.1.24", "about": "a test",
                            "restart": [sys.executable, "-c",
                                        f"open({self.flag!r}, 'w').write('x')"]}}}
        self.gw = gateway.Gateway(self.cfg)
        host, port = self.gw.serve(block=False, poll=0.02)
        self.root = f"http://{host}:{port}"
        self.url = f"{self.root}/v1/saves/t"
        self.key = self.gw.keys.add("ann")
        self.env = mock.patch.dict(os.environ, {"FK_LINK": "gateway", "FK_GATEWAY": self.url,
                                                "FK_GATEWAY_KEY": self.key})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.gw.close()
        self.game.shutdown()
        self.game.server_close()
        self.tmp.cleanup()

    def as_agent(self, name):
        return mock.patch.dict(os.environ, {"FK_GATEWAY_KEY": self.gw.keys.add(name)})

    def journal(self):
        return self.gw.journal_tail("t", 50)


class TestRelayThroughTheGateway(GatewayCase):
    def test_hello_and_lua(self):
        with link.connect() as r:
            self.assertEqual(r.hello["you"], "ann")
            self.assertEqual(r.hello["role"], "visitor")
            self.assertEqual(r.hello["factorio"], "2.1.24")
            self.assertEqual(r.lua("rcon.print('x')"), "ok")
        self.assertEqual(self.game.cmds, ["/sc rcon.print('x')"])
        row = self.journal()[-1]
        self.assertEqual((row["who"], row["cmd"], row["reply"]), ("ann", "/sc rcon.print('x')", 2))

    def test_no_key_and_a_disabled_key(self):
        with mock.patch.dict(os.environ, {"FK_GATEWAY_KEY": "wrong"}):
            r, why = link.open_from_env()
        self.assertIsNone(r)
        self.assertIn("401", why)
        self.gw.keys.set("ann", disabled=True)
        r, why = link.open_from_env()
        self.assertIsNone(r)
        self.gw.keys.set("ann", disabled=False)
        self.assertIsNotNone(link.open_from_env()[0])

    def test_lua_only_and_the_accident_guards(self):
        with link.connect() as r:
            for cmd, word in (("/ban someone", "Lua only"),
                              ("/sc game.tick_paused = true", "pausing"),
                              ("/sc game.speed = 10", "speed"),
                              ("/sc game.server_save('x')", "saves"),
                              ("/sc game.kick_player('rory')", "moderation"),
                              ("/sc game.delete_surface('lab')", "others built")):
                with self.assertRaises(link.LinkError) as e:
                    r.call(cmd)
                self.assertIn("403", str(e.exception))
                self.assertIn(word, str(e.exception))
            # reading them is fine
            r.lua("rcon.print(tostring(game.tick_paused) .. (game.speed == 1 and 'a' or 'b'))")
        self.assertEqual(len(self.game.cmds), 1)
        refused = [row for row in self.journal() if row.get("refused")]
        self.assertEqual(len(refused), 6)

    def test_a_maintainer_passes_the_guards_but_never_registers(self):
        self.gw.keys.set("ann", role="maintainer")
        self.assertIsNone(gateway.guard("/sc game.tick_paused = true", "maintainer"))
        self.assertIn("registers", gateway.guard("/sc script.on_event(1, f)", "maintainer"))
        with link.connect() as r:
            self.assertEqual(r.call("/sc game.server_save('x')"), "ok")

    def test_each_agent_has_its_own_answer_files_and_paste_buffer(self):
        self.assertEqual(gateway.namespace("/sc helpers.write_file('fk5/snap.json', x) "
                                           "storage.fk5_bp = storage.fk5_bp .. 'a'", "Bo-b"),
                         "/sc helpers.write_file('fk5/Bo-b/snap.json', x) "
                         "storage.fk5_bp_bo_b = storage.fk5_bp_bo_b .. 'a'")
        lua = "helpers.write_file('fk5/snap.json', '{}') rcon.print(1)"
        with link.connect() as r:
            got = link.read_output(r, lua.format('{"by": "ann"}'), "snap", "snap")
        with self.as_agent("bob"), link.connect() as r:
            theirs = link.read_output(r, lua.format('{"by": "bob"}'), "snap", "snap", keep=False)
        self.assertEqual((got, theirs), ({"by": "ann"}, {"by": "bob"}))
        self.assertTrue(os.path.exists(os.path.join(self.out, "fk5", "ann", "snap.json")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "fk5", "bob", "snap.json")))

    def test_out_never_leaves_script_output(self):
        s = self.gw.saves["t"]
        for rel in ("../rcon.pw", "/etc/passwd", "fk5/../../rcon.pw", "a/../../x", "c:/x"):
            self.assertIsNone(s.out_path(rel, "ann"), rel)
        self.assertTrue(s.out_path("fk5/a.json", "ann").endswith(
            os.path.join("fk5", "ann", "a.json")))
        with self.assertRaises(link.LinkError) as e:
            link.gateway_get("out/..%2F..%2Frcon.pw")
        self.assertIn("400", str(e.exception))

    def test_the_rate_limit(self):
        self.gw.cfg["limits"]["calls_per_min"] = 4
        with link.connect() as r:                                 # the hello is a request too
            for _ in range(3):
                r.lua("rcon.print(1)")
            with self.assertRaises(link.LinkError) as e:
                r.lua("rcon.print(1)")
        self.assertIn("429", str(e.exception))

    def test_save_pulls_have_their_own_limit(self):
        with open(os.path.join(self.saves, "a.zip"), "wb") as fh:
            fh.write(b"zip")
        self.gw.cfg["limits"]["saves_per_hour"] = 2
        link.gateway_get("save")
        link.gateway_get("save")
        with self.assertRaises(link.LinkError) as e:
            link.gateway_get("save")
        self.assertIn("429", str(e.exception))

    def test_the_journal_cannot_fill_the_disk_and_tells_no_addresses(self):
        self.gw.cfg["limits"]["journal_cmd_bytes"] = 100
        with link.connect() as r:
            r.lua("rcon.print('" + "x" * 500 + "')")
        folder = os.path.join(self.cfg["data"], "journal", "t")
        with open(os.path.join(folder, os.listdir(folder)[0])) as fh:
            row = json.loads(fh.readlines()[-1])
        self.assertEqual((len(row["cmd"]), row["cut"], row["from"]), (100, 518, "127.0.0.1"))
        self.assertEqual(len(row["sha256"]), 64)
        status, body = link.gateway_get("journal")
        self.assertNotIn("from", json.loads(body)[-1])

    def test_remove_reaches_only_the_callers_own_answer_files(self):
        other = os.path.join(self.out, "fk-stats")
        os.makedirs(other)
        with open(os.path.join(other, "samples.jsonl"), "w") as fh:
            fh.write("{}")
        status, body = link.gateway_get("out/fk5/../fk-stats/samples.jsonl", query={"remove": 1})
        self.assertEqual((status, body), (200, b"{}"))            # read, not removed
        self.assertTrue(os.path.exists(os.path.join(other, "samples.jsonl")))

    def test_a_big_body_is_refused(self):
        self.gw.cfg["limits"]["body_bytes"] = 1000
        with link.connect() as r:
            with self.assertRaises(link.LinkError) as e:
                r.lua("rcon.print('" + "x" * 2000 + "')")
        self.assertIn("413", str(e.exception))

    def test_a_stale_save_is_saved_again_before_it_is_handed_out(self):
        old = os.path.join(self.saves, "_autosave1.zip")
        with open(old, "wb") as fh:
            fh.write(b"ten minutes ago")
        self.assertEqual(link.gateway_get("save")[1], b"ten minutes ago")   # fresh enough
        os.utime(old, (time.time() - 600, time.time() - 600))
        self.game.saves = self.saves
        self.assertEqual(link.gateway_get("save")[1], b"as it stands")
        self.assertIn("server_save('gateway')", self.game.cmds[-1])
        n = len(self.game.cmds)
        self.assertEqual(link.gateway_get("save")[1], b"as it stands")      # and not saved twice
        self.assertEqual(len(self.game.cmds), n)

    def test_the_save_is_the_newest_finished_zip(self):
        self.gw.cfg["limits"]["save_age_s"] = 0
        for i, name in enumerate(("old.zip", "new.zip", "newer.tmp.zip")):
            path = os.path.join(self.saves, name)
            with open(path, "wb") as fh:
                fh.write(name.encode())
            os.utime(path, (1000 + i, 1000 + i))
        status, body = link.gateway_get("save")
        self.assertEqual((status, body), (200, b"new.zip"))


class TestRegistration(GatewayCase):
    def test_register_then_play(self):
        key = commons.register(self.url, "new-agent", "owner@example.org")
        with mock.patch.dict(os.environ, {"FK_GATEWAY_KEY": key}), link.connect() as r:
            self.assertEqual(r.hello["you"], "new-agent")
        row = self.gw.keys.agents["new-agent"]
        self.assertNotIn(key, json.dumps(row))                    # only its hash is kept
        self.assertEqual(row["contact"], "owner@example.org")

    def test_names(self):
        for bad in ("ab", "has space", "../x", "-lead", "x" * 40):
            with self.assertRaises(link.LinkError) as e:
                commons.register(self.url, bad)
            self.assertIn("400", str(e.exception))
        with self.assertRaises(link.LinkError) as e:
            commons.register(self.url, "ANN")                      # ann, in other letters
        self.assertIn("409", str(e.exception))

    def test_limits_per_address_and_closing(self):
        self.gw.cfg["register"]["per_address_per_hour"] = 2
        commons.register(self.url, "one1")
        commons.register(self.url, "two2")
        with self.assertRaises(link.LinkError) as e:
            commons.register(self.url, "three3")
        self.assertIn("429", str(e.exception))
        self.gw.cfg["register"]["open"] = False
        with self.assertRaises(link.LinkError) as e:
            commons.register(self.url, "four4")
        self.assertIn("closed", str(e.exception))

    def test_the_proxys_forwarded_address_is_the_agents(self):
        req = urllib.request.Request(
            f"{self.root}/v1/register", data=json.dumps({"name": "far-agent"}).encode(),
            headers={"X-Forwarded-For": "203.0.113.9", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(self.gw.keys.agents["far-agent"]["address"], "203.0.113.9")

    def test_the_keys_command(self):
        cfg_path = os.path.join(self.tmp.name, "gateway.json")
        with open(cfg_path, "w") as fh:
            json.dump(self.cfg, fh)
        self.assertEqual(gateway.main(["keys", "--config", cfg_path, "disable", "ann"]), 0)
        self.assertIsNone(self.gw.keys.who(self.key))              # the running gateway sees it
        self.assertEqual(gateway.main(["keys", "--config", cfg_path, "role", "ann",
                                       "maintainer"]), 0)
        self.assertEqual(gateway.main(["keys", "--config", cfg_path, "enable", "ann"]), 0)
        self.assertEqual(self.gw.keys.who(self.key)[1]["role"], "maintainer")


class TestSharedThings(GatewayCase):
    def test_pages_and_status(self):
        with urllib.request.urlopen(self.root + "/", timeout=5) as resp:
            self.assertEqual(resp.read(), b"# come and play\n")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.root + "/..%2Fdata%2Fagents.json", timeout=5)
        self.gw.probe(self.gw.saves["t"])
        with link.connect() as r:
            r.lua("rcon.print(1)")
        got = commons.status()
        self.assertEqual(got["saves"]["t"]["tick"], 1000)
        self.assertEqual(got["saves"]["t"]["agents_last_hour"], ["ann"])
        self.assertTrue(got["register"])

    def test_the_board(self):
        game = os.path.join(self.tmp.name, "game")
        self.assertEqual(commons.unread(game, "ann"), [])          # the first look starts the count
        with self.as_agent("bob"):
            commons.say("  iron smelting is mine,\n  north of spawn  ")
        commons.say("ok")
        self.assertEqual(self.game.cmds[0],
                         "/sc game.print(\"[bob] iron smelting is mine, north of spawn\") "
                         "rcon.print('ok')")
        notes = commons.unread(game, "ann")
        self.assertEqual([(n["name"], n["text"]) for n in notes],
                         [("bob", "iron smelting is mine, north of spawn")])
        self.assertEqual(commons.footer(game, "ann"),
                         ["BOARD (1): other agents left notes: read them with `fk commons board`"])
        self.assertEqual(commons.main(game, "board", []), 0)       # reading them moves the mark
        self.assertEqual(commons.footer(game, "ann"), [])

    def test_claims_overlap_nobody(self):
        commons.claim("main", [0, 0, 100, 100], "smelters")
        with self.as_agent("bob"):
            with self.assertRaises(link.LinkError) as e:
                commons.claim("main", [50, 50, 150, 150])
            self.assertIn("overlaps ann's plot main", str(e.exception))
            commons.claim("main", [100, 0, 200, 100])              # touching is not overlapping
        got = commons.claims()
        self.assertEqual(got["ann"]["main"]["area"], [0, 0, 100, 100])
        self.assertEqual(sorted(got), ["ann", "bob"])
        commons.claim("main", [0, 0, 60, 60])                      # your own plot moves freely
        commons.claim("main", None)
        self.assertEqual(sorted(commons.claims()), ["bob"])
        self.assertEqual(commons.claim_lines(commons.claims()),
                         ["claim bob/main: 100,0,200,100 (100x100)"])


class TestKeeper(GatewayCase):
    def test_a_hung_server_is_restarted_and_it_says_so(self):
        s = self.gw.saves["t"]
        with link.connect() as r:
            r.lua("rcon.print('the last call')")
        self.game.hang = True
        with mock.patch.object(gateway.Save, "_open", side_effect=socket.timeout("timed out")):
            self.gw.watch(s)
            self.assertFalse(os.path.exists(self.flag))            # one miss is not a hang
            self.gw.watch(s)
        self.assertTrue(os.path.exists(self.flag))
        event = [r for r in self.journal() if r.get("event") == "restart"][0]
        self.assertEqual(event["last"], "ann")
        self.game.hang = False
        self.game.cmds.clear()
        self.gw.watch(s)
        self.assertIn("restarted from its last save", self.game.cmds[-1])
        self.assertIn("ann", self.game.cmds[-1])

    def test_an_empty_save_stands_still_until_someone_comes(self):
        s = self.gw.saves["t"]
        s.cfg["idle_pause_s"] = 600
        self.gw.probe(s)
        self.gw.idle(s)
        self.assertFalse(self.game.paused)                        # somebody was just here
        s.touched -= 700
        self.gw.idle(s)
        self.assertTrue(self.game.paused)
        with link.connect() as r:                                 # an agent's call sets it going
            r.lua("rcon.print(1)")
        self.assertFalse(self.game.paused)
        s.touched -= 700
        self.gw.probe(s)
        self.gw.idle(s)
        self.assertTrue(self.game.paused)
        self.game.players = 1                                     # and so does a player joining
        self.gw.probe(s)
        self.gw.idle(s)
        self.assertFalse(self.game.paused)
        self.gw.idle(s)
        self.assertFalse(self.game.paused)                        # nobody is paused under a player
        events = [r["event"] for r in self.journal() if r.get("event")]
        self.assertEqual(events, ["paused", "resumed", "paused", "resumed"])

    def test_a_call_that_times_out_is_a_504_and_the_next_one_works(self):
        self.game.hang = True
        with link.Relay(timeout=10) as r:
            with self.assertRaises(link.LinkError) as e:
                r.lua("while true do end")
            self.assertIn("504", str(e.exception))
            self.game.hang = False
            self.assertEqual(r.lua("rcon.print(1)"), "ok")
        self.assertTrue(any(row.get("error") for row in self.journal()))

    def test_backups_copy_a_changed_save_and_drop_old_ones(self):
        s = self.gw.saves["t"]
        save = os.path.join(self.saves, "_autosave1.zip")
        with open(save, "wb") as fh:
            fh.write(b"one")
        first = self.gw.backup(s)
        self.assertTrue(first and os.path.exists(first))
        self.assertIsNone(self.gw.backup(s))                       # not yet an hour
        s.last_backup = 0
        self.assertIsNone(self.gw.backup(s))                       # nothing changed
        os.utime(first, (1, 1))                                    # a week old and more
        with open(save, "wb") as fh:
            fh.write(b"two")
        os.utime(save, (time.time() + 5, time.time() + 5))
        s.last_backup = 0
        with mock.patch.object(gateway.time, "strftime", return_value="20990101-000000"):
            second = self.gw.backup(s)
        with open(second, "rb") as fh:
            self.assertEqual(fh.read(), b"two")
        self.assertFalse(os.path.exists(first))

    def test_the_sweep_keeps_script_output_small(self):
        s = self.gw.saves["t"]
        folder = os.path.join(self.out, "fk5", "ann")
        os.makedirs(folder)
        now = time.time()
        for i, (name, age) in enumerate((("stale.json", 90000), ("a.json", 300), ("b.json", 200),
                                         ("c.json", 100))):
            path = os.path.join(folder, name)
            with open(path, "w") as fh:
                fh.write("x" * 1000)
            os.utime(path, (now - age, now - age))
        self.gw.cfg["limits"]["out_bytes"] = 2500
        self.gw.sweep(s)
        self.assertEqual(sorted(os.listdir(folder)), ["b.json", "c.json"])


if __name__ == "__main__":
    unittest.main()
