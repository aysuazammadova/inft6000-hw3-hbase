"""Continuous client traffic used during the chaos experiments.

8 workers, one per region. Every worker loops:
  write a new order (SYNC_WAL)  ->  STRONG read of an acked order  ->  TIMELINE read of an acked order
Once per second it prints one line. The region map shows each region:
  #  all writes succeeded     x  all writes failed     ~  some failed     .  no reply this second

Acknowledged keys are logged so verify.py can prove no acknowledged write was lost.
The per-second numbers are also saved to timeline.csv.
"""
import argparse
import os
import random
import threading
import time
from collections import defaultdict

from common import REGION_NAMES, HBase, row_key, safe_call

lock = threading.Lock()
sec = defaultdict(int)   # counters for the current second
total = defaultdict(int)
stop = threading.Event()


def count(name, region=None, n=1):
    with lock:
        sec[name if region is None else f"{name}{region}"] += n
        total[name] += n


def worker(region, rate, acked_file, failed_file, run_id):
    db = HBase()
    acked = []
    seq = 0
    pause = 1.0 / rate
    while not stop.is_set():
        t0 = time.perf_counter()
        order_id = (seq * 8) + region
        seq += 1
        key = row_key(order_id, f"{run_id}-")
        ok, _, ms, _ = safe_call(db, db.put, key, {"status": "NEW", "amount": order_id % 500, "ts": time.time()})
        if ok:
            count("w_ok", region)
            acked.append(key)
            with lock:
                acked_file.write(key.decode() + "\n")
        else:
            count("w_fail", region)
            with lock:
                failed_file.write(key.decode() + "\n")
        if acked:
            k = random.choice(acked)
            ok, _, _, _ = safe_call(db, db.get, k, "STRONG")
            count("rs_ok" if ok else "rs_fail")
            ok, res, _, _ = safe_call(db, db.get, k, "TIMELINE")
            if ok:
                count("rt_ok")
                if res[1]:
                    count("rt_stale")
            else:
                count("rt_fail")
        elapsed = time.perf_counter() - t0
        if elapsed < pause:
            time.sleep(pause - elapsed)


def region_map(c):
    out = ""
    for r in range(8):
        ok, fail = c.get(f"w_ok{r}", 0), c.get(f"w_fail{r}", 0)
        out += "#" if ok and not fail else "x" if fail and not ok else "~" if ok else "."
    return out


def reporter(start, csv):
    csv.write("time,t,regions,w_ok,w_fail,strong_ok,strong_fail,timeline_ok,timeline_stale,timeline_fail\n")
    while not stop.wait(1.0):
        with lock:
            c = dict(sec)
            sec.clear()
        w_ok = sum(v for k, v in c.items() if k.startswith("w_ok"))
        w_fail = sum(v for k, v in c.items() if k.startswith("w_fail"))
        print(f"{time.strftime('%H:%M:%S')} t={int(time.time() - start):3d}s "
              f"| regions {region_map(c)} "
              f"| writes ok {w_ok:3d} fail {w_fail:3d} "
              f"| STRONG reads ok {c.get('rs_ok', 0):3d} fail {c.get('rs_fail', 0):3d} "
              f"| TIMELINE reads ok {c.get('rt_ok', 0):3d} stale {c.get('rt_stale', 0):3d} fail {c.get('rt_fail', 0):3d}",
              flush=True)
        csv.write(f"{time.strftime('%H:%M:%S')},{int(time.time() - start)},{region_map(c)},{w_ok},{w_fail},"
                  f"{c.get('rs_ok', 0)},{c.get('rs_fail', 0)},{c.get('rt_ok', 0)},{c.get('rt_stale', 0)},{c.get('rt_fail', 0)}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--rate", type=float, default=5, help="write loops per second per region")
    ap.add_argument("--run", default=time.strftime("%H%M%S"))
    a = ap.parse_args()

    out_dir = f"/results/run_{a.run}"
    os.makedirs(out_dir, exist_ok=True)
    acked_file = open(f"{out_dir}/acked.txt", "w", buffering=1)
    failed_file = open(f"{out_dir}/failed.txt", "w", buffering=1)

    print("region map order: " + " ".join(REGION_NAMES), flush=True)
    start = time.time()
    threads = [threading.Thread(target=worker, args=(r, a.rate, acked_file, failed_file, a.run), daemon=True)
               for r in range(8)]
    for t in threads:
        t.start()
    csv = open(f"{out_dir}/timeline.csv", "w", buffering=1)
    rep = threading.Thread(target=reporter, args=(start, csv), daemon=True)
    rep.start()
    time.sleep(a.duration)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    rep.join(timeout=2)

    print("\n== traffic summary ==")
    print(f"writes   ok {total['w_ok']}  failed {total['w_fail']}")
    print(f"STRONG   ok {total['rs_ok']}  failed {total['rs_fail']}")
    print(f"TIMELINE ok {total['rt_ok']}  (stale {total['rt_stale']})  failed {total['rt_fail']}")
    print(f"acked keys: {out_dir}/acked.txt")


if __name__ == "__main__":
    main()
