"""helpers: the player's reusable features (README.md). ``@feature`` registers a function under its
name; ``python -m helpers`` lists them by the first line of their docstrings. Stdlib only."""
from __future__ import annotations

FEATURES = {}


def feature(fn):
    """Register ``fn`` as ``python -m helpers <name>`` (its name, ``_`` written ``-``)."""
    FEATURES[fn.__name__.replace("_", "-")] = fn
    return fn


from . import probes  # noqa: E402,F401  (the seed features register themselves)
