#!/usr/bin/env bash
# Fault-injection experiments, each run while client traffic is active.
#   ./scripts/chaos.sh rs-crash         kill -9 a RegionServer, watch its regions fail over
#   ./scripts/chaos.sh partition        cut a RegionServer off the network, then heal
#   ./scripts/chaos.sh master-failover  kill the active HMaster, backup takes over
#   ./scripts/chaos.sh zk-leader        kill the ZooKeeper leader, ensemble re-elects
#   ./scripts/chaos.sh wal-loss         crash with SKIP_WAL vs SYNC_WAL data in memory
source "$(dirname "$0")/lib.sh"
trap 'kill "${LOGS_PID:-}" 2> /dev/null; docker rm -f hw3-traffic > /dev/null 2>&1; exit 130' INT TERM

mark() {
  say "$*"
  [ -n "${RUN_ID:-}" ] && echo "$(date -u +%H:%M:%S),$*" >> "results/run_$RUN_ID/events.csv"
}

start_traffic() {
  RUN_ID=$(date +%H%M%S)
  mkdir -p "results/run_$RUN_ID"
  docker rm -f hw3-traffic > /dev/null 2>&1
  docker compose run -d --name hw3-traffic client python traffic.py --duration "$1" --run "$RUN_ID" > /dev/null
  docker logs -f hw3-traffic &
  LOGS_PID=$!
}

finish_traffic() {
  docker wait hw3-traffic > /dev/null
  sleep 1
  kill "$LOGS_PID" 2> /dev/null
  docker rm hw3-traffic > /dev/null
  say "Checking that no acknowledged write was lost"
  py verify.py --run "$RUN_ID"
}

run_rs_crash() {
  VICTIM=$(py cluster_info.py --victim)
  py cluster_info.py
  say "Starting traffic. Victim RegionServer: $VICTIM"
  start_traffic 100
  sleep 20
  mark "CRASH: docker kill $VICTIM (SIGKILL, no clean shutdown)"
  docker kill "$VICTIM" > /dev/null
  sleep 45
  mark "RESTART: docker start $VICTIM (it rejoins the cluster with no regions)"
  docker start "$VICTIM" > /dev/null
  finish_traffic
  wait_healthy "$VICTIM"
  balance
  say "Region placement after recovery + balancer"
  py cluster_info.py
}

run_partition() {
  VICTIM=$(py cluster_info.py --victim)
  py cluster_info.py
  say "Starting traffic. RegionServer to isolate: $VICTIM"
  start_traffic 120
  sleep 20
  mark "PARTITION: docker network disconnect hw3net $VICTIM"
  docker network disconnect hw3net "$VICTIM"
  sleep 50
  mark "HEAL: docker network connect hw3net $VICTIM"
  docker network connect hw3net "$VICTIM"
  for _ in $(seq 1 45); do
    [ "$(docker inspect -f '{{.State.Running}}' "$VICTIM")" = false ] && break
    sleep 2
  done
  say "$VICTIM after healing: $(docker inspect -f '{{.State.Status}} (exit code {{.State.ExitCode}})' "$VICTIM")"
  docker logs "$VICTIM" 2>&1 | grep -v ClientCnxn | grep -E 'ABORTING|YouAreDeadException|SessionExpired' | tail -2 | cut -c1-220
  mark "RESTART: $VICTIM rejoins as a new RegionServer instance"
  docker restart "$VICTIM" > /dev/null
  finish_traffic
  wait_healthy "$VICTIM"
  balance
  py cluster_info.py
}

run_master_failover() {
  ACTIVE=$(py cluster_info.py --active-master)
  py cluster_info.py --masters
  say "Starting traffic. Active HMaster: $ACTIVE"
  start_traffic 60
  sleep 15
  mark "CRASH: docker kill $ACTIVE"
  docker kill "$ACTIVE" > /dev/null
  sleep 25
  say "Active HMaster now: $(py cluster_info.py --active-master)"
  mark "RESTART: docker start $ACTIVE (comes back as backup)"
  docker start "$ACTIVE" > /dev/null
  finish_traffic
  wait_healthy "$ACTIVE"
  py cluster_info.py --masters
}

run_zk_leader() {
  LEADER=$(zk_leader)
  zk_modes
  say "Starting traffic. ZooKeeper leader: $LEADER"
  start_traffic 45
  sleep 15
  mark "CRASH: docker kill $LEADER"
  docker kill "$LEADER" > /dev/null
  sleep 5
  say "ZooKeeper ensemble after the leader crash:"
  zk_modes
  sleep 10
  mark "RESTART: docker start $LEADER (rejoins as follower)"
  docker start "$LEADER" > /dev/null
  finish_traffic
  zk_modes
}

run_wal_loss() {
  VICTIM=$(py cluster_info.py --victim)
  TAG="d$(date +%H%M%S)"
  say "Writing rows with SKIP_WAL and SYNC_WAL (they stay in MemStore, not yet flushed)"
  py durability_test.py write --tag "$TAG"
  py durability_test.py check --tag "$TAG"
  mark "CRASH: docker kill $VICTIM"
  docker kill "$VICTIM" > /dev/null
  say "Waiting 40 s for ZooKeeper to expire the session and the HMaster to recover the regions"
  sleep 40
  py durability_test.py check --tag "$TAG"
  mark "RESTART: docker start $VICTIM"
  docker start "$VICTIM" > /dev/null
  wait_healthy "$VICTIM"
  balance
}

case "${1:-}" in
  rs-crash)        run_rs_crash ;;
  partition)       run_partition ;;
  master-failover) run_master_failover ;;
  zk-leader)       run_zk_leader ;;
  wal-loss)        run_wal_loss ;;
  *) sed -n '2,7p' "$0"; exit 1 ;;
esac
