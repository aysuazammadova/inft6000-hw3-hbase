#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  namenode)
    if [ ! -f /data/nn/current/VERSION ]; then
      hdfs namenode -format -nonInteractive
    fi
    exec hdfs namenode
    ;;
  datanode)     exec hdfs datanode ;;
  master)       exec hbase master start ;;
  regionserver) exec hbase regionserver start ;;
  thrift)       exec hbase thrift2 start ;;
  init)         exec bash /opt/hw3/init-table.sh ;;
  *)            exec "$@" ;;
esac
