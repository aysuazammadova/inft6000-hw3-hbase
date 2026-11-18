"""Builds the report figures from results/run_*/timeline.csv and events.csv.

  python report/plot_timelines.py results/run_<rs-crash> results/run_<partition> [run_<master-failover> run_<zk-leader>]
"""
import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def secs(hms):
    h, m, s = map(int, hms.split(":"))
    return h * 3600 + m * 60 + s


def load(run):
    with open(f"{run}/timeline.csv") as f:
        rows = list(csv.DictReader(f))
    events = []
    try:
        with open(f"{run}/events.csv") as f:
            for line in f:
                t, label = line.strip().split(",", 1)
                events.append((t, label.split(":")[0]))
    except FileNotFoundError:
        pass
    return rows, events


def plot(run, title, out, size=(7, 2.6)):
    rows, events = load(run)
    t = [int(r["t"]) for r in rows]
    t0 = secs(rows[0]["time"]) - t[0]
    fig, ax = plt.subplots(figsize=size)
    down = [x for x, r in zip(t, rows) if set(r["regions"]) != {"#"}]
    if down:
        ax.axvspan(min(down) - 0.5, max(down) + 0.5, color="#d62728", alpha=0.08, label="some regions unavailable")
    ax.plot(t, [int(r["w_ok"]) for r in rows], color="#2a6fdb", label="writes OK")
    ax.plot(t, [int(r["w_fail"]) for r in rows], color="#d62728", label="writes failed")
    ax.plot(t, [int(r["timeline_stale"]) for r in rows], color="#ff9f1c", linestyle="--", label="TIMELINE stale reads")
    for hms, label in events:
        x = secs(hms) - t0
        x -= round(x / 3600) * 3600   # host clock and container clock may differ by a time-zone offset
        ax.axvline(x, color="#555555", linestyle=":", linewidth=1)
        ax.text(x + 0.5, ax.get_ylim()[1] * 0.92, label, fontsize=7, color="#333333")
    ax.set_xlabel("time since traffic start (s)")
    ax.set_ylabel("operations / s")
    ax.set_title(title, fontsize=9)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, loc="center right")
    fig.tight_layout()
    fig.savefig(out)
    print("saved", out)


if __name__ == "__main__":
    plot(sys.argv[1], "RegionServer crash (docker kill)", "report/fig/rs_crash.pdf")
    plot(sys.argv[2], "Network partition of a RegionServer", "report/fig/partition.pdf")
    if len(sys.argv) > 4:
        plot(sys.argv[3], "Active HMaster crash", "report/fig/master.pdf", size=(7, 2.2))
        plot(sys.argv[4], "ZooKeeper leader crash", "report/fig/zk.pdf", size=(7, 2.2))
