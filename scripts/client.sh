#!/usr/bin/env bash
# Runs a Python tool inside the client container, e.g. ./scripts/client.sh bench.py
source "$(dirname "$0")/lib.sh"
docker compose run --rm client python "$@"
