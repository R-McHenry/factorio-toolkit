"""setup_v1: the starter world of a V1 run (``fkcore.kickoff_setup``, where it lives since 3.0 so a
run's own toolkit has it for ``fk sim kickoff``).
    python3 kickoff/setup_v1.py [--dry] [--pack seablock]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fkcore.kickoff_setup import *  # noqa: E402,F401,F403
from fkcore.kickoff_setup import main, run  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
