"""3.3 (PLAN-COMMONS): FK_LINK=gateway (link.Relay, read_answer) and fk replica, against a stub
fk-gateway on localhost and a fake headless download."""
import http.server
import io
import json
import os
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock

from fkcore import link, replica
from fkcore import sim as simmod

KEY = "k-test"


class Stub(http.server.BaseHTTPRequestHandler):
    """The gateway protocol of link.Relay: hello, rcon, out/<path>[?remove=1], save."""
    out_dir = None
    calls = []
    replies = []
    save = b"PK-save"

    def log_message(self, *a):
        pass

    def _auth(self):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            self._send(401, b"unknown key")
            return False
        return True

    def _send(self, code, body, kind="application/octet-stream"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._auth():
            return
        u = urllib.parse.urlparse(self.path)
        path = u.path[len("/v1/saves/t/"):]
        if path == "hello":
            body = {"save": "t", "factorio": "2.1.24",
                    "toolkit": self.headers.get("X-FK-Toolkit")}
            return self._send(200, json.dumps(body).encode(), "application/json")
        if path == "save":
            return self._send(200, Stub.save)
        if path.startswith("out/"):
            f = os.path.join(Stub.out_dir, *urllib.parse.unquote(path[4:]).split("/"))
            if not os.path.isfile(f):
                return self._send(404, b"")
            with open(f, "rb") as fh:
                data = fh.read()
            if "remove=1" in (u.query or ""):
                os.remove(f)
            return self._send(200, data)
        self._send(404, b"")

    def do_POST(self):
        if not self._auth():
            return
        n = int(self.headers.get("Content-Length") or 0)
        cmd = json.loads(self.rfile.read(n))["cmd"]
        Stub.calls.append(cmd)
        reply = Stub.replies.pop(0) if Stub.replies else ""
        self._send(200, json.dumps({"reply": reply}).encode(), "application/json")


class GatewayCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/v1/saves/t"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Stub.out_dir = os.path.join(self.tmp.name, "out")
        os.makedirs(os.path.join(Stub.out_dir, "fk5"))
        Stub.calls, Stub.replies = [], []
        self.env = mock.patch.dict(os.environ, {"FK_LINK": "gateway", "FK_GATEWAY": self.url,
                                                "FK_GATEWAY_KEY": KEY, "FK_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def answer(self, tag, data):
        with open(os.path.join(Stub.out_dir, "fk5", f"{tag}.json"), "w") as fh:
            json.dump(data, fh)


class TestRelay(GatewayCase):
    def test_open_from_env_gives_a_relay(self):
        self.assertTrue(link.enabled())
        r, why = link.open_from_env()
        self.assertIsNone(why)
        self.assertIsInstance(r, link.Relay)
        self.assertEqual(r.hello["save"], "t")
        from fkcore import __version__
        self.assertEqual(r.hello["toolkit"], __version__)

    def test_lua_goes_as_one_silent_line(self):
        Stub.replies = ["42"]
        with link.connect() as r:
            got = r.lua("local x = 1  -- a note\nrcon.print(x)\n")
        self.assertEqual(got, "42")
        self.assertEqual(Stub.calls, ["/sc local x = 1 rcon.print(x)"])

    def test_registering_lua_never_leaves(self):
        with link.connect() as r:
            with self.assertRaises(link.LinkError):
                r.lua("script.on_event(defines.events.on_tick, function() end)")
        self.assertEqual(Stub.calls, [])

    def test_a_wrong_key_says_so(self):
        with mock.patch.dict(os.environ, {"FK_GATEWAY_KEY": "nope"}):
            r, why = link.open_from_env()
        self.assertIsNone(r)
        self.assertIn("401", why)
        self.assertIn("unknown key", why)

    def test_no_url_says_so(self):
        with mock.patch.dict(os.environ, {"FK_GATEWAY": ""}):
            r, why = link.open_from_env()
        self.assertIsNone(r)
        self.assertIn("FK_GATEWAY", why)

    def test_read_output_through_the_gateway(self):
        Stub.replies = ["2"]
        self.answer("snap", {"rows": [1, 2]})
        with link.connect() as r:
            got = link.read_output(r, "rcon.print(2)", "snap", "snapshot", keep=False)
        self.assertEqual(got, {"rows": [1, 2]})
        self.assertFalse(os.path.exists(os.path.join(Stub.out_dir, "fk5", "snap.json")))

    def test_read_answer_waits_for_a_late_file(self):
        later = threading.Timer(0.5, self.answer, ("late", {"ok": True}))
        later.start()
        with link.connect() as r:
            t0 = time.monotonic()
            got = link.read_answer(r, "fk5/late.json", "late read", wait=10)
        self.assertEqual(got, {"ok": True})
        self.assertGreater(time.monotonic() - t0, 0.3)

    def test_read_answer_gives_up(self):
        with link.connect() as r:
            with self.assertRaises(link.LinkError):
                link.read_answer(r, "fk5/never.json", "never", wait=0.5)

    def test_rcon_mode_still_reads_out_dir(self):
        with mock.patch.dict(os.environ, {"FK_LINK": "on"}), \
                mock.patch.object(link, "OUT_DIR", Stub.out_dir):
            self.answer("local", {"n": 1})

            class Fake:
                def lua(self, body):
                    return "1"
            self.assertEqual(link.read_output(Fake(), "x", "local", "local read"), {"n": 1})


def _fake_headless():
    """A .tar.xz laid out like Factorio's headless download."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in (("factorio/bin/x64/factorio", b"#!/bin/sh\n"),
                           ("factorio/data/base/info.json", b"{}")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestReplica(GatewayCase):
    def test_build_names(self):
        self.assertEqual(replica.build("Linux", "x86_64"), "linux64")
        self.assertEqual(replica.build("Linux", "aarch64"), "linux-arm64")
        self.assertIsNone(replica.build("Windows", "AMD64"))
        self.assertIsNone(replica.build("Darwin", "arm64"))

    def test_version_is_the_gateways(self):
        self.assertEqual(replica.version(), "2.1.24")
        with mock.patch.dict(os.environ, {"FK_GATEWAY": ""}):
            self.assertEqual(replica.version(), "stable")

    def test_install_and_setup(self):
        asked = []

        def opener(req, timeout=None):
            asked.append(req.full_url)
            self.assertTrue(req.get_header("User-agent").startswith("fkcore/"))
            return io.BytesIO(_fake_headless())
        run = os.path.join(self.tmp.name, "run")
        s = simmod.Sim(run)
        with mock.patch.object(replica, "build", lambda *a: "linux64"):
            exe = replica.setup(s, None, log=lambda *_: None, opener=opener)
            again = replica.install("2.1.24", log=lambda *_: None, opener=opener)
        self.assertEqual(asked, ["https://factorio.com/get-download/2.1.24/headless/linux64"])
        self.assertEqual(exe, again)
        self.assertTrue(exe.endswith(os.path.join("factorio", "bin", "x64", "factorio")))
        self.assertTrue(exe.startswith(os.path.join(self.tmp.name, "factorio", "2.1.24")))
        with mock.patch.dict(os.environ, {"FK_LAPTOP_FACTORIO": ""}):
            self.assertEqual(simmod.Sim(run).exe, exe)

    def test_install_refuses_off_linux(self):
        with mock.patch.object(replica, "build", lambda *a: None):
            with self.assertRaises(replica.ReplicaError) as e:
                replica.install("2.1.24", log=lambda *_: None, opener=None)
        self.assertIn("WSL", str(e.exception))

    def test_pull_writes_the_save_state(self):
        s = simmod.Sim(os.path.join(self.tmp.name, "run"))
        line = replica.pull(s, "live")
        with open(s.save_path("live"), "rb") as fh:
            self.assertEqual(fh.read(), Stub.save)
        self.assertIn("save state live", line)
        self.assertEqual(s.names(), ["live"])

    def test_pull_with_a_wrong_key_leaves_nothing(self):
        s = simmod.Sim(os.path.join(self.tmp.name, "run"))
        with mock.patch.dict(os.environ, {"FK_GATEWAY_KEY": "nope"}):
            with self.assertRaises(replica.ReplicaError):
                replica.pull(s, "live")
        self.assertEqual(s.names(), [])


if __name__ == "__main__":
    unittest.main()
