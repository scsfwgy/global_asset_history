"""Guardrails for the mandatory test-start-log-review delivery workflow."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_start_commands_force_tests_and_reject_legacy_flags():
    script = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "set -o pipefail" in script
    assert "preflight\n    launch_production" in script
    assert "preflight\n    kill_port_if_needed" in script
    assert "FLASK_DEBUG=0 PYTHONUNBUFFERED=1" in script
    assert "HOST=127.0.0.1 FLASK_DEBUG=1 PYTHONUNBUFFERED=1" in script
    assert 'validate_args "$@"' in script
    assert "show_logs" in script
    assert "--test" not in script


def test_ai_delivery_gate_requires_startup_and_log_review():
    instructions = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "产品交付门禁（强制）" in instructions
    assert "./start.sh debug" in instructions
    assert "./start.sh logs" in instructions
    assert "event=app_start" in instructions
    assert "event=http_request" in instructions
    assert "不得声称产品已交付完成" in instructions


@pytest.mark.parametrize("stubborn", [False, True])
def test_port_release_allows_cleanup_and_only_targets_listeners(tmp_path, stubborn):
    import subprocess

    script = (ROOT / "start.sh").read_text()
    function = script.split("kill_port_if_needed() {", 1)[1].split("# ─── 交互菜单", 1)[0]
    calls = tmp_path / "calls"
    count = tmp_path / "count"
    harness = '''
lsof() {
    echo "lsof $*" >> "$CALLS"
    if [ "$STUBBORN" = 1 ]; then
        if [ ! -f "$COUNT" ]; then echo 12345; else return 1; fi
    elif [ ! -f "$COUNT" ]; then echo 12345; touch "$COUNT"; else return 1; fi
}
kill() {
    echo "kill $*" >> "$CALLS"
    if [ "$1" = -KILL ]; then touch "$COUNT"; fi
}
sleep() { :; }
''' + "kill_port_if_needed() {" + function + "\nkill_port_if_needed\n"
    import os
    result = subprocess.run(["bash", "-c", harness], env={**os.environ, "CALLS": str(calls), "COUNT": str(count), "STUBBORN": "1" if stubborn else "0"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    log = calls.read_text()
    assert "kill -TERM 12345" in log
    assert ("kill -KILL 12345" in log) is stubborn
    assert all("-sTCP:LISTEN" in line for line in log.splitlines() if line.startswith("lsof"))
