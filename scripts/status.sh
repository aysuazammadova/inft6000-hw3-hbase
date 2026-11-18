#!/usr/bin/env bash
source "$(dirname "$0")/lib.sh"

echo "== Containers =="
docker compose ps -a --format 'table {{.Name}}\t{{.Status}}'
echo
echo "== ZooKeeper ensemble =="
zk_modes
echo
echo "== HDFS =="
docker exec namenode hdfs dfsadmin -report 2>/dev/null | grep -E 'Live datanodes|Dead datanodes' | sed 's/^/  /'
echo
echo "== HBase =="
py cluster_info.py
