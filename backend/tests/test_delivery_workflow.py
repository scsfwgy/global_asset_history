"""Guardrails for the mandatory test-start-log-review delivery workflow."""

from pathlib import Path


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
