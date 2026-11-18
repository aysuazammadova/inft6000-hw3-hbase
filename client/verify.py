"""Checks a traffic run after a fault:
  - every acknowledged write must be readable (STRONG)  -> lost must be 0
  - failed writes are reported separately: a timeout means "unknown", the write may have committed

  python verify.py            latest run
  python verify.py --run ID   specific run
"""
import argparse
import glob
import os
import sys

from common import HBase


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [line.strip().encode() for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    a = ap.parse_args()
    if a.run:
        run_dir = f"/results/run_{a.run}"
    else:
        runs = sorted(glob.glob("/results/run_*"), key=os.path.getmtime)
        if not runs:
            sys.exit("no traffic runs found in /results")
        run_dir = runs[-1]

    acked, failed = load(f"{run_dir}/acked.txt"), load(f"{run_dir}/failed.txt")
    db = HBase(timeout_ms=30000)
    found_acked = db.exists_many(acked)
    found_failed = db.exists_many(failed)
    lost = len(acked) - len(found_acked)

    print(f"== verify {run_dir} ==")
    print(f"acknowledged writes : {len(acked)}")
    print(f"  readable now      : {len(found_acked)}")
    print(f"  LOST              : {lost}")
    print(f"failed writes       : {len(failed)}")
    print(f"  committed anyway  : {len(found_failed)}  (client gave up, but the server had applied it)")
    print("RESULT: " + ("PASS - no acknowledged write was lost" if lost == 0 else "FAIL - acknowledged writes lost"))
    sys.exit(0 if lost == 0 else 1)


if __name__ == "__main__":
    main()
