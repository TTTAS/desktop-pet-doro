"""Optional Docker execution. No host-shell fallback, pulls or Docker socket mount."""

import os
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from .models import ToolCleanupError

IMAGE = "python:3.12-slim"


def local_docker(docker: str) -> list[str]:
    """Honor local desktop/rootless contexts, but refuse remote Docker hosts."""
    endpoint = os.environ.get("DOCKER_HOST", "")
    if os.environ.get("DOCKER_CONTEXT") or not endpoint:
        try:
            context = subprocess.run(
                [docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("無法檢查 Docker context。") from None
        if context.returncode:
            raise ValueError("Docker context 尚未就緒。")
        endpoint = context.stdout.decode("utf-8").strip()
    if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
        raise ValueError("只允許這台電腦上的 Docker（Unix socket 或 Windows named pipe）。")
    return [docker, "--host", endpoint]


def docker_command(docker: str, workspace: Path, name: str, argv: list[str]) -> list[str]:
    if "," in str(workspace):
        raise ValueError("容器工作目錄路徑不能含逗號。")
    uid = getattr(os, "getuid", lambda: 1000)() or 65534
    gid = getattr(os, "getgid", lambda: 1000)() or 65534
    return [
        docker,
        "run",
        "--rm",
        "--pull=never",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=256m",
        "--memory-swap=256m",
        "--cpus=1",
        "--user",
        f"{uid}:{gid}",
        "--workdir=/work",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
        "--log-driver=none",
        "--mount",
        f"type=bind,source={workspace},target=/work",
        *[
            f"--env={key}="
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "no_proxy",
            )
        ],
        "--env=HOME=/tmp",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        f"--entrypoint={argv[0]}",
        IMAGE,
        *argv[1:],
    ]


def run_command(
    workspace: Path, argv: list[str], timeout: int, cancelled: Callable[[], bool]
) -> str:
    docker = shutil.which("docker")
    if not docker:
        raise ValueError("未安裝 Docker，指令工具不可用；不會改用主機 shell。")
    docker_prefix = local_docker(docker)
    name = "doro-task-" + uuid.uuid4().hex
    args = docker_prefix + docker_command(docker, workspace, name, argv)[1:]
    if cancelled():
        raise ValueError("已取消，未啟動容器。")
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = bytearray()
    overflow = threading.Event()

    def read_output():
        total = 0
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            total += len(chunk)
            output.extend(chunk[: max(0, 12000 - len(output))])
            if total > 1024 * 1024:
                overflow.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    problem = ""
    try:
        while process.poll() is None:
            if cancelled() or time.monotonic() >= deadline or overflow.is_set():
                problem = "指令已取消／逾時／輸出超過 1 MiB，已停止容器。"
                break
            overflow.wait(0.05)
    finally:
        # rm -f removes the container, not only the Docker client process.
        # Always attempt it: cancellation can race successful process exit.
        try:
            cleanup = subprocess.run(
                [*docker_prefix, "rm", "-f", name], capture_output=True, timeout=10, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            cleanup = None
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=5)
        process.stdout.close()
        if cleanup is None or (cleanup.returncode and b"No such container" not in cleanup.stderr):
            raise ToolCleanupError(f"無法確認容器 {name} 已清理，任務停止；請檢查 Docker。")
    if overflow.is_set():
        problem = "指令輸出超過 1 MiB，已停止容器。"
    if problem:
        raise ValueError(problem)
    text = bytes(output).decode("utf-8", errors="replace")[:5500]
    if process.returncode:
        raise ValueError(
            f"容器指令失敗（exit {process.returncode}）。Docker／映像可能未就緒。\n{text}"
        )
    return f"exit=0\n{text}" + ("\n[輸出已截斷]" if len(output) >= 5500 else "")
