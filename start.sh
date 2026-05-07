#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

VENV_PYTHON="backend/.venv/bin/python3"
VENV_PIP="backend/.venv/bin/pip"
PIDFILE="logs/server.pid"
LOGFILE="logs/server.log"

setup() {
    echo "[1/2] 安装依赖..."
    if [ ! -d backend/.venv ]; then
        python3 -m venv backend/.venv
    fi
    $VENV_PIP install -q -r backend/requirements.txt
    mkdir -p logs
}

start_production() {
    setup
    echo "[2/2] 启动服务 (后台模式)..."
    PYTHONPATH=backend nohup "$VENV_PYTHON" backend/app.py >> "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "  服务已启动 PID: $(cat $PIDFILE)"
    echo "  访问: http://127.0.0.1:8730"
    echo "  日志: $LOGFILE"
}

start_debug() {
    setup
    echo "[2/2] 启动服务 (调试模式)..."
    echo "  访问: http://127.0.0.1:8730"
    echo "  按 Ctrl+C 停止"
    echo ""
    PYTHONPATH=backend "$VENV_PYTHON" backend/app.py
}

stop() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        kill "$PID" 2>/dev/null && echo "已停止服务 (PID: $PID)" || echo "服务未运行"
        rm -f "$PIDFILE"
    else
        echo "服务未运行"
    fi
}

status() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "运行中 (PID: $PID)"
        else
            echo "已停止 (PID 文件残留)"
            rm -f "$PIDFILE"
        fi
    else
        echo "未运行"
    fi
}

case "${1:-}" in
    start|production)
        start_production
        ;;
    debug)
        start_debug
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start_production
        ;;
    status)
        status
        ;;
    *)
        echo "用法: ./start.sh [命令]"
        echo ""
        echo "  无参数      调试模式 (前台, 自动重载)"
        echo "  start       生产模式 (后台静默运行)"
        echo "  stop        停止后台服务"
        echo "  restart     重启后台服务"
        echo "  status      查看服务状态"
        echo ""
        start_debug
        ;;
esac
