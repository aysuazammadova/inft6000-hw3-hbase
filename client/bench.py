"""Baseline benchmark: how durability and read consistency settings change latency,
throughput and data freshness.

  1. Writes with SKIP_WAL / ASYNC_WAL / SYNC_WAL
  2. Reads with STRONG (primary only) / TIMELINE (any replica)
  3. Freshness: write a new value, read it back immediately from secondary replica 1
"""
import argparse
import json
import os
import time

from common import HBase, percentile, row_key, safe_call


def stats(lat, seconds):
    return {
        "ops": len(lat),
        "ops_per_s": round(len(lat) / seconds, 1),
        "p50_ms": round(percentile(lat, 50), 2),
        "p95_ms": round(percentile(lat, 95), 2),
        "p99_ms": round(percentile(lat, 99), 2),
    }


def bench_writes(db, mode, n, base):
    lat = []
    t0 = time.perf_counter()
    for i in range(n):
        s = time.perf_counter()
        db.put(row_key(base + i, "b"), {"status": "NEW", "amount": i % 500, "mode": mode}, durability=mode)
        lat.append((time.perf_counter() - s) * 1000)
    return stats(lat, time.perf_counter() - t0)


def bench_reads(db, consistency, keys):
    lat, stale = [], 0
    t0 = time.perf_counter()
    for k in keys:
        s = time.perf_counter()
        _, is_stale = db.get(k, consistency)
        lat.append((time.perf_counter() - s) * 1000)
        stale += is_stale
    out = stats(lat, time.perf_counter() - t0)
    out["stale_reads"] = stale
    return out


def read_replica(db, key):
    ok, res, _, _ = safe_call(db, db.get, key, "TIMELINE", replica_id=1)
    return res[0] if ok else None


def bench_freshness(db, n, max_wait=5.0):
    """Read-your-writes from a secondary replica: how often is the value not there yet, and for how long."""
    first_stale, never, lags = 0, 0, []
    for i in range(n):
        key = row_key(900000 + i, "f")
        value = str(time.time_ns())
        db.put(key, {"v": value})
        t_write = time.perf_counter()
        vals = read_replica(db, key)
        if vals is None or vals.get("v") != value:
            first_stale += 1
            while time.perf_counter() - t_write < max_wait:
                vals = read_replica(db, key)
                if vals and vals.get("v") == value:
                    break
                time.sleep(0.002)
            else:
                never += 1
                continue
        lags.append((time.perf_counter() - t_write) * 1000)
    return {
        "reads": n,
        "stale_first_read": first_stale,
        "stale_pct": round(100 * first_stale / n, 1),
        "not_visible_after_5s": never,
        "lag_p50_ms": round(percentile(lags, 50), 2),
        "lag_p95_ms": round(percentile(lags, 95), 2),
        "lag_max_ms": round(max(lags), 2) if lags else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=2000, help="writes per durability mode")
    ap.add_argument("--fresh", type=int, default=100, help="freshness probes")
    a = ap.parse_args()
    db = HBase()
    results = {"writes": {}, "reads": {}}

    bench_writes(db, "SYNC_WAL", 500, base=5_000_000)   # warm-up: connections, region locations, JIT

    print(f"== 1. Writes ({a.rows} per mode, one client) ==")
    print(f"{'durability':12s} {'ops/s':>8s} {'p50 ms':>8s} {'p95 ms':>8s} {'p99 ms':>8s}")
    for idx, mode in enumerate(["SKIP_WAL", "ASYNC_WAL", "SYNC_WAL"]):
        r = bench_writes(db, mode, a.rows, base=idx * 1_000_000)
        results["writes"][mode] = r
        print(f"{mode:12s} {r['ops_per_s']:8.1f} {r['p50_ms']:8.2f} {r['p95_ms']:8.2f} {r['p99_ms']:8.2f}")

    keys = [row_key(2_000_000 + i, "b") for i in range(a.rows)]
    print(f"\n== 2. Reads ({a.rows} existing rows) ==")
    print(f"{'consistency':12s} {'ops/s':>8s} {'p50 ms':>8s} {'p95 ms':>8s} {'p99 ms':>8s} {'stale':>6s}")
    for c in ["STRONG", "TIMELINE"]:
        r = bench_reads(db, c, keys)
        results["reads"][c] = r
        print(f"{c:12s} {r['ops_per_s']:8.1f} {r['p50_ms']:8.2f} {r['p95_ms']:8.2f} {r['p99_ms']:8.2f} {r['stale_reads']:6d}")

    print(f"\n== 3. Freshness: write, then read at once from secondary replica ({a.fresh} probes) ==")
    r = bench_freshness(db, a.fresh)
    results["freshness"] = r
    print(f"old value on first read: {r['stale_first_read']}/{r['reads']} ({r['stale_pct']}%)")
    print(f"never visible within 5 s: {r['not_visible_after_5s']}")
    print(f"time until replica has the new value: p50 {r['lag_p50_ms']} ms, p95 {r['lag_p95_ms']} ms, max {r['lag_max_ms']} ms")

    os.makedirs("/results", exist_ok=True)
    path = f"/results/bench_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    main()
