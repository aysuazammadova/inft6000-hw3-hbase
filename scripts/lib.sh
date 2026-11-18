cd "$(dirname "${BASH_SOURCE[0]}")/.."

py() { docker compose run --rm -T client python "$@"; }

say() { printf '\n\033[1;33m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }

zk_modes() {
  for z in zk1 zk2 zk3; do
    printf '  %s: %s\n' "$z" "$(docker exec "$z" zkServer.sh status 2>/dev/null | grep -o 'Mode: .*' || echo down)"
  done
}

zk_leader() {
  for z in zk1 zk2 zk3; do
    docker exec "$z" zkServer.sh status 2>/dev/null | grep -q 'Mode: leader' && echo "$z"
  done
}

wait_healthy() {
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$1")" = healthy ]; do sleep 2; done
}

balance() {
  sleep 10
  echo "balancer" | docker exec -i thrift hbase shell -n > /dev/null 2>&1
  sleep 10
}

save_logs() {
  mkdir -p results/logs
  for c in $(docker ps -a --filter network=hw3net --format '{{.Names}}'); do
    docker logs --tail 400 "$c" > "results/logs/$c.log" 2>&1
  done
  echo "container logs saved in results/logs/"
}
