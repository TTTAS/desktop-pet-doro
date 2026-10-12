"""Subprocess lifecycle with a fake Docker CLI; real-container checks are opt-in."""

import json
import sys
import threading

import pytest

from doro_app.core.agent import sandbox


@pytest.fixture
def docker(tmp_path, monkeypatch):
    log = tmp_path / "calls.jsonl"
    cli = tmp_path / "docker-fixture"
    cli.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        f"with open({str(log)!r}, 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if 'context' in sys.argv:\n"
        "    print('unix:///tmp/test-docker.sock')\n"
        "elif 'rm' in sys.argv:\n"
        "    pass\n"
        "elif 'run' in sys.argv:\n"
        "    mode = sys.argv[-1]\n"
        "    if mode == 'sleep': time.sleep(10)\n"
        "    elif mode == 'failure': print('bad command'); sys.exit(7)\n"
        "    elif mode == 'missing': print('image not found'); sys.exit(125)\n"
        "    elif mode == 'flood': print('x' * 1100000)\n"
        "    else: print('RESULT')\n"
    )
    # Run the CLI fixture via Python on Windows too (no POSIX shebang assumption).
    original_popen = sandbox.subprocess.Popen
    original_run = sandbox.subprocess.run

    def translate(args):
        return [sys.executable, str(cli), *args[1:]] if args[0] == "fixture-docker" else args

    def popen(args, *positional, **kwargs):
        return original_popen(translate(args), *positional, **kwargs)

    def invoke(args, *positional, **kwargs):
        return original_run(translate(args), *positional, **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "Popen", popen)
    monkeypatch.setattr(sandbox.subprocess, "run", invoke)
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "fixture-docker")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    workspace = tmp_path / "work"
    workspace.mkdir()
    return workspace, log


def test_command_success_is_bounded_and_cleans_container(docker):
    workspace, log = docker
    result = sandbox.run_command(workspace, ["python", "success"], 3, lambda: False)
    assert result.splitlines() == ["exit=0", "RESULT"]
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    invocation = next(call for call in calls if "run" in call)
    for flag in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--pull=never",
        "--pids-limit=64",
        "--security-opt=no-new-privileges",
    ):
        assert flag in invocation
    assert invocation.count("--mount") == 1
    assert f"type=bind,source={workspace},target=/work" in invocation
    assert "--privileged" not in invocation
    assert calls[-1][2:4] == ["rm", "-f"]
    assert calls[-1][-1] == invocation[invocation.index("--name") + 1]


@pytest.mark.parametrize(
    "mode, message",
    [("failure", "exit 7"), ("missing", "exit 125"), ("sleep", "逾時"), ("flood", "1 MiB")],
)
def test_failures_cleanup_without_host_fallback(docker, mode, message):
    workspace, log = docker
    with pytest.raises(ValueError, match=message):
        sandbox.run_command(workspace, ["python", mode], 1, lambda: False)
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert sum("run" in call for call in calls) == 1
    assert "rm" in calls[-1]


def test_cancellation_removes_container_not_only_client(docker):
    workspace, log = docker
    cancelled = threading.Event()
    timer = threading.Timer(0.1, cancelled.set)
    timer.start()
    try:
        with pytest.raises(ValueError, match="取消"):
            sandbox.run_command(workspace, ["python", "sleep"], 5, cancelled.is_set)
    finally:
        timer.cancel()
    assert "rm" in json.loads(log.read_text(encoding="utf-8").splitlines()[-1])


def test_missing_docker_never_launches_host_command(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="未安裝"):
        sandbox.run_command(tmp_path, ["python", "-c", "raise Exception()"], 1, lambda: False)


def test_remote_docker_is_refused_before_any_execution(docker, monkeypatch):
    workspace, log = docker
    monkeypatch.setenv("DOCKER_HOST", "ssh://another-computer")
    with pytest.raises(ValueError, match="這台電腦"):
        sandbox.run_command(workspace, ["python", "success"], 1, lambda: False)
    assert not log.exists()


def test_cancel_before_launch_does_not_create_container(docker):
    workspace, log = docker
    with pytest.raises(ValueError, match="取消"):
        sandbox.run_command(workspace, ["python", "success"], 1, lambda: True)
    assert all(
        "run" not in json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
    )
