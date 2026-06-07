#!/usr/bin/env bash
set -e

export DISPLAY="${DISPLAY:-:99}"
export SCREEN_WIDTH="${SCREEN_WIDTH:-1920}"
export SCREEN_HEIGHT="${SCREEN_HEIGHT:-1080}"
export SCREEN_DEPTH="${SCREEN_DEPTH:-24}"

mkdir -p /app/browser_data /app/data /tmp/.X11-unix

echo "[entrypoint] starting Xvfb on ${DISPLAY}"
Xvfb "${DISPLAY}" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +render -noreset &

for _ in $(seq 1 30); do
  if xdpyinfo -display "${DISPLAY}" >/tmp/xdpyinfo.log 2>&1; then
    break
  fi
  sleep 1
done

if ! xdpyinfo -display "${DISPLAY}" >/tmp/xdpyinfo.log 2>&1; then
  echo "[entrypoint] Xvfb failed to become ready on ${DISPLAY}" >&2
  cat /tmp/xdpyinfo.log >&2 || true
  exit 1
fi

echo "[entrypoint] starting window manager"
fluxbox >/tmp/fluxbox.log 2>&1 &

echo "[entrypoint] starting x11vnc"
x11vnc \
  -display "${DISPLAY}" \
  -forever \
  -shared \
  -nopw \
  -listen 0.0.0.0 \
  -xkb \
  >/tmp/x11vnc.log 2>&1 &

echo "[entrypoint] starting noVNC on :6080"
websockify --web=/usr/share/novnc/ 0.0.0.0:6080 localhost:5900 >/tmp/novnc.log 2>&1 &

echo "[entrypoint] starting MediaCrawler WebUI"
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8080
