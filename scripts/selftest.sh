#!/usr/bin/env bash
# End-to-end check: build, start, benchmark and every chaos scenario. Output also goes to results/selftest.log
source "$(dirname "$0")/lib.sh"
exec > >(tee results/selftest.log) 2>&1
trap 'echo "interrupted"; docker rm -f hw3-traffic > /dev/null 2>&1; exit 130' INT TERM

step() { printf '\n\n########## %s  [%s] ##########\n' "$*" "$(date +%H:%M:%S)"; }

step "Docker"
docker version --format 'client {{.Client.Version}}, server {{.Server.Version}}' || exit 1
docker info --format 'CPUs {{.NCPU}}, memory {{.MemTotal}} bytes'

step "Build images and start the cluster"
docker compose up -d --build || { save_logs; exit 1; }

step "Create table"
docker wait init > /dev/null
docker logs init 2>&1 | grep '\[init\]'

step "Cluster status"
./scripts/status.sh

step "Benchmark"
py bench.py

for s in rs-crash partition master-failover zk-leader wal-loss; do
  step "Chaos: $s"
  ./scripts/chaos.sh "$s"
done

step "Final status"
balance
./scripts/status.sh
save_logs
step "Done"
