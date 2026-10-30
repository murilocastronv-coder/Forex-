#!/usr/bin/env bash
set -euo pipefail

export WINEPREFIX="${WINEPREFIX:-/opt/wineprefix}"
export DISPLAY="${DISPLAY:-:99}"

Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp &
XVFB_PID=$!
cleanup() { kill "$XVFB_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
  sleep 1
done

MT5_EXE="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"
if [ ! -f "$MT5_EXE" ]; then
  echo "MT5 terminal not found at expected path: $MT5_EXE" >&2
  find "$WINEPREFIX/drive_c/Program Files" -iname terminal64.exe -print >&2 || true
  exit 1
fi

wine "$MT5_EXE" /portable &
python3 poc_app.py
