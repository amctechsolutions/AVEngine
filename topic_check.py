#!/usr/bin/env python3
"""
Pre-flight check for a script spec BEFORE spending any voice credits: does real footage exist for every scene?
Uses STRICT matching (every query word must be in the clip's tags), so "snapping shrimp" can't pass on a generic shrimp.

  python3 topic_check.py spec.json [--sources pixabay,nasa]
Exit code 1 if any scene has zero exact-match footage.
"""
import argparse, json, sys, time
from pathlib import Path
import stock_footage as sf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--sources", default="pixabay", help="comma list: pixabay,nasa")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    srcs = [x.strip() for x in a.sources.split(",")]
    zero, weak = [], []
    print(f"{spec.get('slug', a.spec)}  (strict matching)")
    print(f"{'#':>2} {'query':26s} {'pixabay':>8} {'portrait':>9} {'nasa':>5}  status")
    for i, sg in enumerate(spec["segments"], 1):
        q = sg.get("query") or sg.get("label", "")
        n = port = 0
        if "pixabay" in srcs:
            c = sf.pixabay_candidates(q, strict=True)
            n, port = len(c), sum(x["portrait"] for x in c)
            time.sleep(0.8)  # stay well inside Pixabay's rate limit
        nasa = ""
        if "nasa" in srcs:
            nasa = "yes" if sf.search(q, providers=["nasa"], strict=True) else "no"
        have = n + (1 if nasa == "yes" else 0)
        status = "ZERO - change query/topic" if have == 0 else ("weak (<3)" if have < 3 else "ok")
        (zero if have == 0 else weak if have < 3 else []).append(i)
        print(f"{i:>2} {q[:26]:26s} {n:>8} {port:>9} {nasa:>5}  {status}")
    print(f"\nzero-footage scenes: {zero or 'none'} | weak: {weak or 'none'}")
    sys.exit(1 if zero else 0)


if __name__ == "__main__":
    main()
