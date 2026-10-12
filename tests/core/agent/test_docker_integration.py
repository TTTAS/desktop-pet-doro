"""Real container acceptance. Preinstall python:3.12-slim; tests never pull it."""

import os
import subprocess
import threading
import uuid
from types import SimpleNamespace

import pytest

from doro_app.core.agent import sandbox

pytestmark = pytest.mark.skipif(
    os.environ.get("DORO_DOCKER_TESTS") != "1", reason="opt-in local Docker integration"
)


@pytest.fixture
def container(tmp_path, monkeypatch):
    # Give this test one known name so its teardown can check for orphan containers.
    unique = uuid.uuid4().hex
    monkeypatch.setattr(sandbox.uuid, "uuid4", lambda: SimpleNamespace(hex=unique))
    docker = sandbox.shutil.which("docker")
    assert docker, "Install Docker and python:3.12-slim before enabling these tests"
    prefix = sandbox.local_docker(docker)
    workspace = tmp_path / "work"
    workspace.mkdir()
    yield workspace
    name = "doro-task-" + unique
    remaining = subprocess.run(
        [*prefix, "ps", "-aq", "--filter", f"name=^{name}$"],
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert not remaining.stdout.strip(), f"Container was not cleaned up: {name}"


def test_container_can_write_only_workspace_and_has_no_network(container):
    code = """
import os, pathlib, socket
assert os.geteuid() != 0
assert not pathlib.Path('/var/run/docker.sock').exists()
status = pathlib.Path('/proc/self/status').read_text(encoding="utf-8")
assert 'CapEff:\\t0000000000000000' in status
assert 'NoNewPrivs:\\t1' in status
try:
    pathlib.Path('/outside').write_text('forbidden')
    raise AssertionError('root is writable')
except OSError:
    pass
with socket.socket() as sock:
    sock.settimeout(0.2)
    try:
        sock.connect(('1.1.1.1', 443))
        raise AssertionError('network is reachable')
    except OSError:
        pass
pathlib.Path('/work/result.txt').write_text('isolated')
print('verified')
"""
    assert "verified" in sandbox.run_command(container, ["python", "-c", code], 15, lambda: False)
    assert (container / "result.txt").read_text(encoding="utf-8") == "isolated"


def test_timeout_reaps_actual_container(container):
    with pytest.raises(ValueError, match="逾時"):
        sandbox.run_command(
            container, ["python", "-c", "import time; time.sleep(30)"], 2, lambda: False
        )


def test_cancel_reaps_actual_container(container):
    cancelled = threading.Event()
    timer = threading.Timer(2, cancelled.set)
    timer.start()
    try:
        with pytest.raises(ValueError, match="取消"):
            sandbox.run_command(
                container, ["python", "-c", "import time; time.sleep(30)"], 15, cancelled.is_set
            )
    finally:
        timer.cancel()
