#!/usr/bin/env bash
set -e

export DISPLAY="${DISPLAY:-:99}"
export SCREEN_WIDTH="${SCREEN_WIDTH:-1920}"
export SCREEN_HEIGHT="${SCREEN_HEIGHT:-1080}"
export SCREEN_DEPTH="${SCREEN_DEPTH:-24}"

XVFB_PID=""
FLUXBOX_PID=""
X11VNC_PID=""
NOVNC_PID=""
UVICORN_PID=""

DISPLAY_NUMBER="${DISPLAY#:}"
DISPLAY_NUMBER="${DISPLAY_NUMBER%%.*}"
X_LOCK="/tmp/.X${DISPLAY_NUMBER}-lock"
X_SOCKET="/tmp/.X11-unix/X${DISPLAY_NUMBER}"

cleanup() {
  trap - EXIT INT TERM

  for pid in "${UVICORN_PID}" "${NOVNC_PID}" "${X11VNC_PID}" "${FLUXBOX_PID}" "${XVFB_PID}"; do
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done

  for pid in "${UVICORN_PID}" "${NOVNC_PID}" "${X11VNC_PID}" "${FLUXBOX_PID}" "${XVFB_PID}"; do
    if [ -n "${pid}" ]; then
      wait "${pid}" 2>/dev/null || true
    fi
  done

  if [ -n "${XVFB_PID}" ]; then
    rm -f "${X_LOCK}" "${X_SOCKET}"
  fi
}

shutdown() {
  echo "[entrypoint] received shutdown signal, stopping services"
  cleanup
  exit 143
}

trap cleanup EXIT
trap shutdown INT TERM

mkdir -p /app/browser_data /app/data /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

if xdpyinfo -display "${DISPLAY}" >/tmp/xdpyinfo.log 2>&1; then
  echo "[entrypoint] X display ${DISPLAY} is already available"
else
  if [ -e "${X_LOCK}" ] || [ -e "${X_SOCKET}" ]; then
    echo "[entrypoint] removing stale X display files for ${DISPLAY}"
    rm -f "${X_LOCK}" "${X_SOCKET}"
  fi

  echo "[entrypoint] starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +render -noreset &
  XVFB_PID="$!"
fi

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
FLUXBOX_PID="$!"

echo "[entrypoint] starting x11vnc"
x11vnc \
  -display "${DISPLAY}" \
  -forever \
  -shared \
  -nopw \
  -listen 0.0.0.0 \
  -xkb \
  >/tmp/x11vnc.log 2>&1 &
X11VNC_PID="$!"

echo "[entrypoint] starting noVNC on :6080"
websockify --web=/usr/share/novnc/ 0.0.0.0:6080 localhost:5900 >/tmp/novnc.log 2>&1 &
NOVNC_PID="$!"

echo "[entrypoint] starting MediaCrawler WebUI"

# ★ 开发热重载
#
# 背景：镜像里的代码是 docker build 阶段 COPY 进去的，之后无论
#   docker compose down / up -d 多少次，都不会把宿主机新改的代码带进容器
#   （up -d 发现镜像已存在会直接复用，不会重新 build）。
#
# 开启 MEDIACRAWLER_DEV_RELOAD=true 后 uvicorn 会监听源码变化自动重启，
# 配合 docker-compose.dev.yml 的代码卷挂载，即可做到「改完即生效，不用重建」。
# 仅用于开发调试；生产请保持 false（reload 会额外占资源且不宜常驻）。
UVICORN_ARGS="api.main:app --host 0.0.0.0 --port 8080"
if [ "${MEDIACRAWLER_DEV_RELOAD:-false}" = "true" ]; then
  # uvicorn 的 --reload 依赖 watchfiles 包。
  # 基础镜像未预装时【不能让容器起不来】，这里检测后优雅降级：
  # 没装就退回普通模式并提示，保证服务始终能启动。
  if python -c "import watchfiles" >/dev/null 2>&1; then
    echo "[entrypoint] dev reload enabled: 源码变更将自动重启 WebUI"
    UVICORN_ARGS="${UVICORN_ARGS} --reload --reload-dir /app"
  else
    echo "[entrypoint] 警告: 未安装 watchfiles，无法启用热重载，以普通模式启动" >&2
    echo "[entrypoint] 修复: docker exec mediacrawler /app/.venv/bin/pip install watchfiles" >&2
    echo "[entrypoint]      或重新构建镜像（Dockerfile 已包含该依赖）" >&2
  fi
fi

python -m uvicorn ${UVICORN_ARGS} &
UVICORN_PID="$!"

set +e
wait "${UVICORN_PID}"
EXIT_CODE="$?"
set -e

exit "${EXIT_CODE}"
