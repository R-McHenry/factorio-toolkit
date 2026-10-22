"""The PostToolUse hook of a Claude Code player (claude_loop.py passes it with --settings).

    python claude_hook.py RUN

The goal loop's watcher writes what the player must not miss into RUN\\.loop: game chat and
INBOX.md as notes (notes-pending.txt), and the world line (world.txt: the ghosts that wait and
what the network lacks). After the player's next shell command this hook hands them to it as
additional context, whatever that command's output kept (a `| head` or `| grep` cuts fk's own
footer, not this): each note once (then kept in notes-sent.txt), the world line when it is new.

2.0 (a lead player and its workers): the notes are the lead's. A tool call inside a worker (the
hook's input names an ``agent_id``) takes nothing, so they wait for the lead's own next shell
command, or for the Agent tool's return: the loop runs this hook after both.
"""
import json
import os
import sys


def notes(d):
    """The pending notes, once: the file is renamed before it is read, so a note is never lost to
    the watcher appending at the same moment, nor given twice."""
    pend = os.path.join(d, "notes-pending.txt")
    mine = f"{pend}.{os.getpid()}"
    try:
        os.replace(pend, mine)
    except OSError:
        return ""
    with open(mine, encoding="utf-8") as f:
        text = f.read().strip()
    with open(os.path.join(d, "notes-sent.txt"), "a", encoding="utf-8") as f:
        f.write(text + "\n\n")
    os.remove(mine)
    return text


def world(d):
    """The world line, when it is not the one handed over last."""
    try:
        with open(os.path.join(d, "world.txt"), encoding="utf-8") as f:
            line = f.read().strip()
    except OSError:
        return ""
    given = os.path.join(d, "world-given.txt")
    try:
        with open(given, encoding="utf-8") as f:
            if f.read().strip() == line:
                return ""
    except OSError:
        pass
    with open(given, "w", encoding="utf-8") as f:
        f.write(line + "\n")
    return line


def take(run):
    d = os.path.join(run, ".loop")
    return "\n\n".join(t for t in (notes(d), world(d)) if t)


def in_worker(raw):
    """True when the hook's input is a tool call inside a subagent (a worker): Claude Code names
    the subagent in ``agent_id``."""
    try:
        return bool(json.loads(raw).get("agent_id"))
    except (ValueError, AttributeError):
        return False


def main():
    try:
        raw = sys.stdin.read()
    except OSError:
        raw = ""
    if in_worker(raw):
        return 0
    text = take(sys.argv[1])
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
