"""The unanswered-chat queue (2.0.25).

Rory, 2026-10-25: "have a handful of sources that make the message pop up, and then the one way the
model can dismiss them". The queue is the source the player sees on every command; `fk ack` is the
one way to dismiss it.

Before this, the cursor moved on *read*: a chat line printed into a command whose output the player
piped through `| Select-Object -First N` was consumed unseen and never shown again (42 of run 1133's
201 fk results lost their footer this way).
"""
import json
import os
import re
import tempfile
import unittest

from fkcore import chat


class Fake:
    """A game link: answers the journal read with the messages a scenario would keep."""

    def __init__(self, tick, msgs, journal=True):
        self.tick, self.msgs, self.journal = tick, [dict(m) for m in msgs], journal
        self.writes = []

    def lua(self, code):
        m = re.search(r"if m\.tick > (\d+) then", code)
        since = int(m.group(1)) if m else 0
        if "INSERT" in code or "message =" in code:
            self.writes.append(code)
            return ""
        return json.dumps({"tick": self.tick, "journal": self.journal,
                           "messages": [x for x in self.msgs if x["tick"] > since]})


ROXY = {"tick": 100, "name": "Rory_618", "message": "there is no furnace bug"}


class ChatAckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def acked(self):
        path = os.path.join(self.dir, chat.ACK)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["tick"]

    def test_first_use_never_replays_history(self):
        r = Fake(1000, [ROXY])
        self.assertEqual(chat.pending(r, self.dir), [])
        self.assertEqual(self.acked(), 1000)
        self.assertEqual(chat.pending(r, self.dir), [])

    def test_a_message_repeats_on_every_command_until_acked(self):
        r = Fake(1000, [])
        chat.pending(r, self.dir)                       # first use, watermark at 1000
        r.tick, r.msgs = 1200, [{"tick": 1100, "name": "Rory_618", "message": "belt the ore"}]
        first = chat.pending(r, self.dir)
        second = chat.pending(r, self.dir)              # a second command: still there
        self.assertIn("UNANSWERED CHAT (1)", first[0])
        self.assertIn("belt the ore", first[1])
        self.assertEqual(first, second)

    def test_ack_is_the_one_way_to_dismiss(self):
        r = Fake(1000, [])
        chat.pending(r, self.dir)
        r.tick, r.msgs = 1200, [{"tick": 1100, "name": "Rory_618", "message": "one"}]
        self.assertTrue(chat.pending(r, self.dir))
        self.assertEqual(chat.ack(r, self.dir), 1200)
        self.assertEqual(chat.pending(r, self.dir), [])

    def test_an_age_is_shown_and_two_messages_count(self):
        r = Fake(1000, [])
        chat.pending(r, self.dir)
        r.tick = 1000 + 4 * 60 * 60                     # four minutes later
        r.msgs = [{"tick": 1000 + 60, "name": "Rory_618", "message": "a"},
                  {"tick": 1000 + 120, "name": "supervisor", "message": "b"}]
        lines = chat.pending(r, self.dir)
        self.assertIn("UNANSWERED CHAT (2)", lines[0])
        self.assertIn("4 min ago", lines[1])
        self.assertIn("supervisor", lines[2])

    def test_a_map_with_no_journal_says_so(self):
        r = Fake(1000, [], journal=False)
        self.assertIn("no chat journal", chat.pending(r, self.dir)[0])


if __name__ == "__main__":
    unittest.main()
