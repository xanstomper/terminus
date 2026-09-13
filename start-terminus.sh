#!/bin/bash
# Terminus - The endpoint you can reach anywhere
set -e

PORT=${PORT:-9120}
HOST=${HOST:-0.0.0.0}

LAN_IP=$(ip -4 addr show scope global | grep inet | awk '{print $2}' | cut -d/ -f1 | head -n1)
if [ -z "$LAN_IP" ]; then
  LAN_IP="127.0.0.1"
fi

echo "=========================================================="
echo " Terminus — The endpoint you can reach anywhere"
echo "=========================================================="
echo " Local Access:  http://localhost:${PORT}"
echo " Phone Access:  http://${LAN_IP}:${PORT}"
echo " Default Login: admin / terminus"
echo "=========================================================="

cd /home/jewboy420/terminus
exec python3 -m uvicorn app:app --host "$HOST" --port "$PORT"
