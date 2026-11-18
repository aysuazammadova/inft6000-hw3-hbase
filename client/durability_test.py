"""Shows what the WAL buys: rows written with SKIP_WAL live only in the RegionServer's memory
(MemStore) until a flush, so a crash loses them. SYNC_WAL rows are replayed from the WAL on HDFS.

  python durability_test.py write --tag T1   (before the crash)
  python durability_test.py check --tag T1   (after recovery)
"""
import argparse
import time

from common import REGION_NAMES, HBase, region_of, row_key


def keys(tag, mode, n):
    return [row_key(i, f"{tag}-{mode}-") for i in range(n)]


def write(db, tag, n):
    for mode in ["SKIP_WAL", "SYNC_WAL"]:
        for k in keys(tag, mode, n):
            db.put(k, {"mode": mode, "ts": time.time()}, durability=mode)
        print(f"wrote {n} rows with {mode}")


def check(db, tag, n):
    print(f"{'durability':10s} {'written':>8s} {'present':>8s} {'lost':>6s}   lost per region")
    for mode in ["SKIP_WAL", "SYNC_WAL"]:
        ks = keys(tag, mode, n)
        found = db.exists_many(ks)
        lost = [k for k in ks if k not in found]
        per_region = {}
        for k in lost:
            per_region[REGION_NAMES[region_of(k)]] = per_region.get(REGION_NAMES[region_of(k)], 0) + 1
        detail = ", ".join(f"{r}:{c}" for r, c in sorted(per_region.items())) or "-"
        print(f"{mode:10s} {n:8d} {len(found):8d} {len(lost):6d}   {detail}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["write", "check"])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n", type=int, default=400)
    a = ap.parse_args()
    db = HBase(timeout_ms=30000)
    write(db, a.tag, a.n) if a.action == "write" else check(db, a.tag, a.n)
