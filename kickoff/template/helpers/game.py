"""game: reads through the run's own ``fk lua`` (the footer comes with it, as with any fk command)."""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.dirname(HERE)
LUA = os.path.join(HERE, "lua")


def lua(name, **subs):
    """Run ``lua/<name>.lua`` (each ``{KEY}`` in it replaced by ``subs[KEY]``) with ``fk lua``;
    -> what it printed."""
    with open(os.path.join(LUA, f"{name}.lua"), encoding="utf-8") as fh:
        text = fh.read()
    for key, value in subs.items():
        text = text.replace("{" + key + "}", str(value))
    # one argument, no shell: fk sends it to the game on its ssh's stdin, quotes and lines as they are
    r = subprocess.run([sys.executable, os.path.join(RUN, "bin", "fk.py"), "lua", text],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=RUN)
    return (r.stdout + r.stderr).rstrip()
