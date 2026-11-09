"""Compare sealed units' compile keys: one build's ``units.json`` across the instances of each
module, or two builds' against each other (3.1.5, 42-reroute).

    python tools/unit_keys.py GAME/out/design/world/units.json
    python tools/unit_keys.py BEFORE.json AFTER.json

The route step writes ``out/design/<factory>/units.json``: each sealed unit's module, key, what
it was laid from, its nets and the key's parts as short shas (``route.part_shas``). One file:
each module's instances that key apart, and the parts that differ. Two files: each unit whose key
changed, and in which parts. Stdlib only.
"""
import json
import sys


def _differ(pa, pb):
    return sorted(n for n in set(pa) | set(pb) if pa.get(n) != pb.get(n))


def across_instances(a):
    by = {}
    for u, c in a.items():
        by.setdefault(c["module"], []).append(u)
    for mod, us in sorted(by.items()):
        keys = {a[u]["key"] for u in us}
        if len(us) < 2:
            continue
        print(f"{mod}: {len(us)} instances, {len(keys)} key{'s' if len(keys) != 1 else ''}")
        if len(keys) < 2:
            continue
        base = us[0]
        for u in us[1:]:
            names = _differ(a[base]["parts"], a[u]["parts"])
            if names:
                print(f"   {u} vs {base}: {', '.join(names)}")


def across_builds(a, b):
    same = changed = 0
    for u in sorted(set(a) | set(b)):
        if u not in a or u not in b:
            print(f"{u}: only in {'the first' if u in a else 'the second'}")
            continue
        if a[u]["key"] == b[u]["key"]:
            same += 1
            continue
        changed += 1
        names = _differ(a[u]["parts"], b[u]["parts"])
        print(f"{u} ({a[u]['module']}): {a[u]['from']} -> {b[u]['from']}; differs in "
              f"{', '.join(names)}")
    print(f"{same} units with the same key, {changed} changed")


def main(argv):
    if not argv or len(argv) > 2:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        a = json.load(fh)
    if len(argv) == 1:
        across_instances(a)
    else:
        with open(argv[1], encoding="utf-8") as fh:
            b = json.load(fh)
        across_builds(a, b)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
