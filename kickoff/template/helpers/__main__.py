"""python -m helpers [FEATURE [ARGS...]]: list the features, or run one."""
import sys

from . import FEATURES


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        for name in sorted(FEATURES):
            doc = (FEATURES[name].__doc__ or "").strip().splitlines()
            print(f"{name:<20} {doc[0] if doc else ''}")
        return 0
    fn = FEATURES.get(argv[0])
    if fn is None:
        print(f"helpers: no feature {argv[0]!r} (python -m helpers lists them)", file=sys.stderr)
        return 2
    out = fn(*argv[1:])
    if out is not None:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
