import os
import socket
import time

from thrift.protocol import TBinaryProtocol
from thrift.transport import TSocket, TTransport

from hbase_thrift import THBaseService
from hbase_thrift.ttypes import (TColumnValue, TConsistency, TDurability, TGet,
                                 TIOError, TPut)

THRIFT_HOST = os.environ.get("THRIFT_HOST", "thrift")
THRIFT_PORT = int(os.environ.get("THRIFT_PORT", "9090"))
TABLE = b"orders"
FAMILY = b"d"

# The table is pre-split on the first character of the row key: 8 regions.
SALTS = "02468ace"
REGION_NAMES = ["[  ,2)", "[2,4)", "[4,6)", "[6,8)", "[8,a)", "[a,c)", "[c,e)", "[e,  )"]

DURABILITY = {
    "SKIP_WAL": TDurability.SKIP_WAL,
    "ASYNC_WAL": TDurability.ASYNC_WAL,
    "SYNC_WAL": TDurability.SYNC_WAL,
}
CONSISTENCY = {
    "STRONG": TConsistency.STRONG,
    "TIMELINE": TConsistency.TIMELINE,
}


def row_key(order_id, prefix="o"):
    """Salted row key: <salt>-<prefix><id>. The salt spreads sequential ids over all regions."""
    return f"{SALTS[order_id % 8]}-{prefix}{order_id:08d}".encode()


def region_of(key):
    return SALTS.index(chr(key[0]))


class HBase:
    """Small wrapper around one Thrift2 connection."""

    def __init__(self, timeout_ms=6000):
        self.timeout_ms = timeout_ms
        self._open()

    def _open(self):
        sock = TSocket.TSocket(THRIFT_HOST, THRIFT_PORT)
        sock.setTimeout(self.timeout_ms)
        self.transport = TTransport.TBufferedTransport(sock)
        self.client = THBaseService.Client(TBinaryProtocol.TBinaryProtocol(self.transport))
        self.transport.open()

    def reconnect(self):
        try:
            self.transport.close()
        except Exception:
            pass
        self._open()

    def put(self, key, values, durability="SYNC_WAL"):
        cols = [TColumnValue(FAMILY, q.encode(), str(v).encode()) for q, v in values.items()]
        self.client.put(TABLE, TPut(row=key, columnValues=cols, durability=DURABILITY[durability]))

    def get(self, key, consistency="STRONG", replica_id=None):
        """Returns (values, stale). values is None if the row does not exist."""
        g = TGet(row=key, consistency=CONSISTENCY[consistency], targetReplicaId=replica_id)
        r = self.client.get(TABLE, g)
        if not r.columnValues:
            return None, bool(r.stale)
        return {c.qualifier.decode(): c.value.decode() for c in r.columnValues}, bool(r.stale)

    def exists_many(self, keys):
        found = set()
        for i in range(0, len(keys), 200):
            chunk = keys[i:i + 200]
            for r in self.client.getMultiple(TABLE, [TGet(row=k) for k in chunk]):
                if r.row:
                    found.add(r.row)
        return found

    def region_locations(self, table=TABLE):
        return self.client.getAllRegionLocations(table)


def safe_call(db, fn, *args, **kwargs):
    """Runs one operation. Returns (ok, result, latency_ms, error_name)."""
    t0 = time.perf_counter()
    try:
        res = fn(*args, **kwargs)
        return True, res, (time.perf_counter() - t0) * 1000, None
    except TIOError:
        return False, None, (time.perf_counter() - t0) * 1000, "HBaseError"
    except (TTransport.TTransportException, socket.timeout, OSError):
        try:
            db.reconnect()
        except Exception:
            pass
        return False, None, (time.perf_counter() - t0) * 1000, "Timeout"


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))
    return s[k]
