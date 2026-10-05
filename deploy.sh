#!/usr/bin/env bash
# ============================================================
# MediaCrawler 一键部署脚本
#
# 解决的问题：
#   docker compose down && docker compose up -d  【不会】更新代码
#   因为代码是 docker build 阶段 COPY 进镜像的快照，
#   down 只删容器不删镜像，up -d 发现镜像存在就直接复用，不会重新 build。
#
# 用法：
#   ./deploy.sh          镜像模式（默认）：检测源码变化，有变化才重建，然后启动
#   ./deploy.sh dev      开发模式：源码热挂载 + uvicorn 热重载，改完即生效
#   ./deploy.sh rebuild  强制全量重建（忽略缓存与哈希，依赖更新时用）
#   ./deploy.sh status   查看当前部署模式与源码变更状态
#
# 环境变量：
#   COMPOSE  指定 compose 命令，默认 "docker compose"（老版本可用 docker-compose）
# ============================================================

set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="${COMPOSE:-docker compose}"
MODE="${1:-image}"
HASH_FILE=".deploy_src_hash"

# 需要纳入「代码是否变化」判断的目录/文件类型
compute_hash() {
    find . \
        -type f \
        \( -name '*.py' -o -name '*.sh' -o -name '*.yml' -o -name '*.yaml' \
           -o -name 'Dockerfile' -o -name '*.toml' -o -name '*.lock' \
           -o -name '*.json' -o -name '*.html' -o -name '*.js' -o -name '*.vue' \) \
        -not -path './data/*' \
        -not -path './browser_data/*' \
        -not -path './.venv/*' \
        -not -path './node_modules/*' \
        -not -path './.git/*' \
        -not -path './docs/*' \
        -print0 2>/dev/null \
    | sort -z \
    | xargs -0 md5sum 2>/dev/null \
    | md5sum \
    | awk '{print $1}'
}

current_hash="$(compute_hash)"
saved_hash=""
[ -f "${HASH_FILE}" ] && saved_hash="$(cat "${HASH_FILE}" 2>/dev/null || true)"

image_exists() {
    docker image inspect mediacrawler:latest >/dev/null 2>&1 && return 0
    # compose v2 镜像名形如 <project>-mediacrawler，这里回退判断服务是否已有镜像
    docker images --format '{{.Repository}}' 2>/dev/null | grep -q 'mediacrawler' && return 0
    return 1
}

echo "=============================================="
echo " MediaCrawler 部署"
echo " 模式: ${MODE}"
echo " 源码指纹: ${current_hash}"
echo " 上次部署: ${saved_hash:-（无记录）}"
echo "=============================================="

case "${MODE}" in

    status)
        if [ -z "${saved_hash}" ]; then
            echo "状态: 无部署记录"
        elif [ "${saved_hash}" = "${current_hash}" ]; then
            echo "状态: 源码与上次部署一致，无需重建"
        else
            echo "状态: ★ 源码已变更，需要重建"
        fi
        echo
        ${COMPOSE} ps
        exit 0
        ;;

    dev)
        echo
        echo "[dev] 开发模式：源码热挂载 + uvicorn 热重载"
        # 首次仍要 build 一次，把依赖（.venv / playwright / 系统包）装进镜像
        if ! image_exists; then
            echo "[dev] 未发现已有镜像，先构建一次（之后改代码无需再构建）..."
            ${COMPOSE} build mediacrawler
        fi
        echo "[dev] 启动（挂载源码，改完自动重载）..."
        ${COMPOSE} -f docker-compose.yml -f docker-compose.dev.yml up -d
        echo
        echo "[dev] 已启动。现在改宿主机上的 .py 文件，容器内会自动生效。"
        echo "[dev] 查看日志: ${COMPOSE} logs -f mediacrawler"
        exit 0
        ;;

    rebuild)
        echo
        echo "[rebuild] 强制全量重建（--no-cache）..."
        ${COMPOSE} build --no-cache mediacrawler
        ${COMPOSE} up -d
        echo "${current_hash}" > "${HASH_FILE}"
        echo "[rebuild] 完成"
        exit 0
        ;;

    image|*)
        need_build="no"
        if ! image_exists; then
            echo "[image] 未发现已有镜像 -> 需要构建"
            need_build="yes"
        elif [ "${saved_hash}" != "${current_hash}" ]; then
            echo "[image] ★ 检测到源码变更 -> 需要重建"
            need_build="yes"
        else
            echo "[image] 源码未变化，跳过构建"
        fi

        if [ "${need_build}" = "yes" ]; then
            echo "[image] 构建镜像（Docker 层缓存会复用未变动的依赖层）..."
            ${COMPOSE} build mediacrawler
        fi

        echo "[image] 启动容器..."
        ${COMPOSE} up -d
        echo "${current_hash}" > "${HASH_FILE}"
        echo
        echo "[image] 完成"
        ${COMPOSE} ps
        ;;
esac
