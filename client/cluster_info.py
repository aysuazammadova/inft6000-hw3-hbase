"""Shows where every region of 'orders' lives and which HMaster is active.

  python cluster_info.py                 full report
  python cluster_info.py --victim        RegionServer to crash (most primaries, does not host hbase:meta)
  python cluster_info.py --active-master hostname of the active HMaster
  python cluster_info.py --masters       role of each HMaster
"""
import argparse
import json
import urllib.request
from collections import Counter, defaultdict

from common import HBase

MASTERS = ["hmaster1", "hmaster2"]
JMX = "http://{}:16010/jmx?qry=Hadoop:service=HBase,name=Master,sub=Server"


def master_role(host):
    try:
        with urllib.request.urlopen(JMX.format(host), timeout=3) as r:
            beans = json.load(r)["beans"]
    except Exception:
        return "down"
    if beans and str(beans[0].get("tag.isActiveMaster")).lower() == "true":
        return "active"
    return "backup"


def region_table(db):
    regions = defaultdict(dict)
    for loc in db.region_locations():
        info = loc.regionInfo
        start = (info.startKey or b"").decode() or "-"
        regions[start][info.replicaId or 0] = loc.serverName.hostName
    return dict(sorted(regions.items()))


def meta_host(db):
    for loc in db.region_locations(b"hbase:meta"):
        if not loc.regionInfo.replicaId:
            return loc.serverName.hostName
    return None


def pick_victim(db):
    primaries = Counter(r.get(0) for r in region_table(db).values())
    meta = meta_host(db)
    candidates = [(n, h) for h, n in primaries.items() if h and h != meta]
    return max(candidates)[1] if candidates else primaries.most_common(1)[0][0]


def masters():
    print("HMasters:")
    for m in MASTERS:
        print(f"  {m:10s} {master_role(m)}")


def report(db):
    masters()
    print(f"\nhbase:meta is on: {meta_host(db)}\n")
    print("Table 'orders' (8 regions x 3 replicas)")
    print(f"  {'start key':10s} {'primary':10s} {'replica 1':10s} {'replica 2':10s}")
    regions = region_table(db)
    for start, reps in regions.items():
        print(f"  {start:10s} {reps.get(0, '?'):10s} {reps.get(1, '?'):10s} {reps.get(2, '?'):10s}")
    count = Counter(r.get(0) for r in regions.values())
    print("\nPrimary regions per RegionServer: " + ", ".join(f"{h}={n}" for h, n in sorted(count.items())))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--victim", action="store_true")
    ap.add_argument("--active-master", action="store_true")
    ap.add_argument("--masters", action="store_true")
    a = ap.parse_args()
    if a.active_master:
        print(next((m for m in MASTERS if master_role(m) == "active"), "none"))
    elif a.masters:
        masters()
    elif a.victim:
        print(pick_victim(HBase()))
    else:
        report(HBase())
