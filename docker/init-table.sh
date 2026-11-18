#!/usr/bin/env bash
set -uo pipefail

echo "[init] waiting for 3 live RegionServers"
until status=$(echo "status" | hbase shell -n 2>/dev/null | grep "servers"); echo "[init] $status"; echo "$status" | grep -Eq "(^|[^0-9])3 servers"; do
  sleep 5
done

if echo "exists 'orders'" | hbase shell -n 2>/dev/null | grep -q "does exist"; then
  echo "[init] table 'orders' already exists"
else
  echo "[init] creating table 'orders' (8 regions x 3 replicas)"
  hbase shell -n /opt/hw3/create_table.rb
fi
# secondary replicas serve reads only after the primary has flushed once
echo "flush 'orders'" | hbase shell -n > /dev/null 2>&1
echo "[init] done"
