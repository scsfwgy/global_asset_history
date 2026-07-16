#!/bin/bash
set -e
set -o pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 自动加载本地密钥（.env.local 不进 git，存放 WISH_ADMIN_TOKEN 等）
if [ -f .env.local ]; then
    set -a
    . ./.env.local
    set +a
fi

VENV_PYTHON="backend/.venv/bin/python3"
VENV_PIP="backend/.venv/bin/pip"
PIDFILE="logs/server.pid"
LOGFILE="logs/server.log"

# ─── 工具函数 ───

setup() {
    echo "[1/3] 安装依赖..."
    if [ ! -d backend/.venv ]; then
        python3 -m venv backend/.venv
    fi
    "$VENV_PIP" install -q -r requirements.txt
    mkdir -p logs
}

wait_for_url() {
    local url="$1"
    for _ in $(seq 1 30); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "启动超时: $url" >&2
    return 1
}

validate_args() {
    if [ "$#" -gt 1 ]; then
        echo "非法参数: ${*:2}" >&2
        echo "提示: debug、start 和 restart 都会强制运行完整测试，无需额外参数。" >&2
        exit 1
    fi
}

# ─── 操作函数 ───

run_test_suite() {
    echo "[2/3] 运行完整测试套件..."
    echo ""
    if PYTHONPATH=backend "$VENV_PYTHON" -m pytest backend/tests/ -v --tb=short --color=yes; then
        echo ""
        echo "[test] ✓ 全部测试通过"
    else
        local exit_code=$?
        echo ""
        echo "[test] ✗ 测试失败 (exit code: $exit_code)，已阻止启动" >&2
        return "$exit_code"
    fi
}

preflight() {
    setup
    run_test_suite
}

launch_production() {
    local port="${PORT:-8730}"
    kill_port_if_needed
    echo "[3/3] 启动服务 (生产模式，后台运行)..."
    echo "[log] production 会话开始 $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOGFILE"
    FLASK_DEBUG=0 PYTHONUNBUFFERED=1 PYTHONPATH=backend \
        nohup "$VENV_PYTHON" backend/app.py >> "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    wait_for_url "http://127.0.0.1:${port}/api/health"
    echo "  服务已启动 PID: $(cat "$PIDFILE")"
    echo "  Flask Debug: off"
    echo "  访问: http://127.0.0.1:${port}"
    echo "  日志: $LOGFILE"
    echo ""
    tail -n 12 "$LOGFILE"
}

start_production() {
    preflight
    launch_production
}

start_debug() {
    local port="${PORT:-8730}"
    preflight
    kill_port_if_needed
    echo "[3/3] 启动服务 (调试模式，前台运行)..."
    echo "  Flask Debug: on（自动重载，仅监听本机）"
    echo "  访问: http://127.0.0.1:${port}"
    echo "  日志: $LOGFILE"
    echo "  按 Ctrl+C 停止"
    echo ""
    echo "[log] debug 会话开始 $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOGFILE"
    HOST=127.0.0.1 FLASK_DEBUG=1 PYTHONUNBUFFERED=1 PYTHONPATH=backend \
        "$VENV_PYTHON" backend/app.py 2>&1 | tee -a "$LOGFILE"
}

stop() {
    if [ -f "$PIDFILE" ]; then
        local pid
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "正在停止服务 (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            for _ in $(seq 1 5); do
                if ! kill -0 "$pid" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PIDFILE"
        echo "  已停止"
    else
        echo "服务未运行"
    fi
}

status() {
    local port="${PORT:-8730}"
    if [ -f "$PIDFILE" ]; then
        local pid
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "运行中 (PID: $pid)"
            echo "访问: http://127.0.0.1:${port}"
        else
            echo "已停止 (PID 文件残留)"
            rm -f "$PIDFILE"
        fi
    else
        echo "未运行"
    fi
}

run_tests() {
    setup
    run_test_suite
}

restart_production() {
    preflight
    stop
    sleep 1
    launch_production
}

show_logs() {
    local lines="${LOG_LINES:-80}"
    if [ ! -f "$LOGFILE" ]; then
        echo "暂无日志: $LOGFILE"
        return 0
    fi
    tail -n "$lines" "$LOGFILE"
}

kill_port_if_needed() {
    local port="${PORT:-8730}"
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "端口 $port 被 PID $pids 占用，正在释放..."
        kill -9 $pids 2>/dev/null || true
        sleep 0.5
        # Double-check: if still occupied, kill again
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null || true
            sleep 0.5
        fi
    fi
}

# ─── 交互菜单 ───

choose_mode() {
    echo ""
    echo "请选择启动模式:"
    echo "  1. debug    (前台，自动重载)"
    echo "  2. production (后台运行)"
    echo "  3. 取消"
    printf "请输入选项编号: "
    local choice
    read -r choice
    case "$choice" in
        1) start_debug ;;
        2) start_production ;;
        3) echo "已取消" ; exit 0 ;;
        *) echo "无效选项" ; exit 1 ;;
    esac
}

interactive_menu() {
    echo "============================================"
    echo "  历年涨跌幅 — GlobalAssetHistory"
    echo "============================================"
    echo ""
    echo "请选择操作:"
    echo "  1. 启动服务"
    echo "  2. 停止服务"
    echo "  3. 重启服务"
    echo "  4. 查看状态"
    echo "  5. 运行测试"
    echo "  6. 退出"
    printf "请输入选项编号: "
    local choice
    read -r choice
    echo ""
    case "$choice" in
        1) choose_mode ;;
        2) stop ;;
        3) restart_production ;;
        4) status ;;
        5) run_tests ;;
        6) echo "已退出" ; exit 0 ;;
        *) echo "无效选项" ; exit 1 ;;
    esac
}

# ─── 入口 ───

validate_args "$@"

case "${1:-}" in
    start|production)
        start_production
        ;;
    debug)
        start_debug
        ;;
    test)
        run_tests
        ;;
    stop)
        stop
        ;;
    restart)
        restart_production
        ;;
    status)
        status
        ;;
    logs)
        show_logs
        ;;
    "")
        interactive_menu
        ;;
    *)
        echo "用法: ./start.sh [命令]"
        echo ""
        echo "  无参数             交互式菜单"
        echo "  start               完整测试通过后，以生产模式后台启动"
        echo "  debug               完整测试通过后，以调试模式前台启动"
        echo "  test                仅运行测试套件"
        echo "  stop                停止服务"
        echo "  restart             完整测试通过后重启生产服务"
        echo "  status              查看状态"
        echo "  logs                查看最近服务日志（LOG_LINES 可指定行数）"
        echo ""
        echo "启动命令不接受额外参数；测试是不可跳过的启动前置步骤。"
        exit 1
        ;;
esac
