"""Registered tools: schemas, exact confirmation previews and bounded effects."""

from __future__ import annotations

import difflib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FilePath(Arguments):
    path: str = Field(min_length=1, max_length=512)


class Directory(Arguments):
    path: str = Field(default=".", min_length=1, max_length=512)


class WriteFile(FilePath):
    text: str = Field(max_length=6000)


class Command(Arguments):
    argv: list[str] = Field(min_length=1, max_length=32)
    timeout_seconds: int = Field(default=30, ge=1, le=60)


class WebURL(Arguments):
    url: str = Field(min_length=1, max_length=2000)


class Query(Arguments):
    query: str = Field(min_length=1, max_length=1000)


class WebGoal(Arguments):
    goal: str = Field(min_length=1, max_length=2000)


@dataclass
class PreparedTool:
    run: Callable[[], str]
    confirmation: str = ""


@dataclass
class Tool:
    description: str
    arguments: type[BaseModel]
    prepare: Callable[[BaseModel], PreparedTool]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def add(self, name: str, description: str, arguments: type[BaseModel], prepare: Callable):
        if name in self._tools:
            raise ValueError("工具名稱重複。")
        self._tools[name] = Tool(description, arguments, prepare)

    def describe(self) -> dict:
        return {
            name: {"description": tool.description, "arguments": tool.arguments.model_json_schema()}
            for name, tool in self._tools.items()
        }

    def prepare(self, name: str, arguments: dict) -> PreparedTool:
        if name not in self._tools:
            raise ValueError("這個工具未開放。")
        tool = self._tools[name]
        try:
            params = tool.arguments.model_validate(arguments)
        except ValueError:
            raise ValueError("工具參數不符合 schema；請依工具表修正。") from None
        return tool.prepare(params)


class Workspace:
    """Dedicated user-owned workspace, never the home directory or filesystem root.

    Refuse links and special files, including hard links. Recheck before commit.
    This is a path boundary, not an OS sandbox against concurrent hostile host
    processes; commands use the separate container boundary.
    """

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
            raise ValueError("工作目錄不能是符號連結。")
        self.root = root.resolve()

    def path(self, name: str) -> Path:
        parts = PurePosixPath(name)
        reserved = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        if (
            not name
            or "\\" in name
            or ":" in name
            or "\x00" in name
            or parts.is_absolute()
            or ".." in parts.parts
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or any(
                part.endswith((" ", ".")) or part.split(".")[0].upper() in reserved
                for part in parts.parts
            )
        ):
            raise ValueError("只接受工作目錄內的相對路徑，不接受 .. 或絕對路徑。")
        current = self.root
        for part in parts.parts:
            current = current / part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise ValueError("不允許符號連結或 junction。")
            if current.exists():
                info = current.stat()
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise ValueError("只接受一般檔案或目錄。")
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise ValueError("不允許硬連結。")
        if not current.resolve().is_relative_to(self.root):
            raise ValueError("路徑超出工作目錄。")
        return current

    def _read(self, name: str) -> bytes:
        path = self.path(name)
        if not path.is_file():
            raise ValueError("找不到一般文字檔。")
        with path.open("rb") as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError("檔案超過 64 KiB，請先拆分。")
        if b"\0" in data:
            raise ValueError("不接受二進位檔案。")
        return data

    def read(self, params: FilePath) -> str:
        try:
            text = self._read(params.path).decode("utf-8")
        except UnicodeError:
            raise ValueError("只支援 UTF-8 文字檔。") from None
        return text[:5500] + ("\n[已截斷，檔案超過 5500 字]" if len(text) > 5500 else "")

    def list(self, params: Directory) -> str:
        path = self.path(params.path)
        if not path.is_dir():
            raise ValueError("找不到目錄。")
        entries = []
        # Do not materialize an unbounded directory, including one made by a command.
        with os.scandir(path) as iterator:
            for item in iterator:
                if len(entries) == 200:
                    entries.append("[最多顯示 200 筆]")
                    break
                entries.append(item.name + ("/" if item.is_dir(follow_symlinks=False) else ""))
        return json.dumps(sorted(entries), ensure_ascii=False)[:5500]

    def write(self, params: WriteFile) -> PreparedTool:
        target = self.path(params.path)
        if not target.parent.is_dir():
            raise ValueError("父目錄不存在；請使用已存在的目錄。")
        old = self._read(params.path) if target.exists() else None
        try:
            old_text = old.decode("utf-8") if old is not None else ""
        except UnicodeError:
            raise ValueError("只支援 UTF-8 文字檔。") from None
        data = params.text.encode("utf-8")
        if b"\0" in data:
            raise ValueError("不接受二進位內容。")
        diff = "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                params.text.splitlines(keepends=True),
                fromfile="原檔",
                tofile=params.path,
            )
        )
        if len(diff) > 12000:
            raise ValueError("變更太大，無法完整預覽；請拆成較小的任務。")

        def commit():
            current = self.path(params.path)
            now = self._read(params.path) if current.exists() else None
            if now != old:
                raise ValueError("確認期間檔案已變更，沒有覆蓋；請重新讀取。")
            fd, temporary = tempfile.mkstemp(prefix=".doro-", dir=current.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Recheck after writing the temporary file as well.
                current = self.path(params.path)
                if (self._read(params.path) if current.exists() else None) != old:
                    raise ValueError("檔案已變更，沒有覆蓋。")
                os.replace(temporary, current)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return f"已寫入 {params.path}（{len(data)} bytes）；請用 file.read 驗證內容。"

        return PreparedTool(
            commit,
            f"寫入工作目錄：{self.root}\n檔案：{params.path}\n完整變更：\n{diff or '(空檔／內容相同)'}",
        )


def local_tools(workspace: Workspace, cancelled: Callable[[], bool]) -> ToolRegistry:
    from .sandbox import run_command

    registry = ToolRegistry()
    registry.add(
        "file.list",
        "列出工作目錄（最多 200 筆）。",
        Directory,
        lambda p: PreparedTool(lambda: workspace.list(p)),
    )
    registry.add(
        "file.read",
        "讀取 UTF-8 文字（最多 5500 字，超出會標示）。",
        FilePath,
        lambda p: PreparedTool(lambda: workspace.read(p)),
    )
    registry.add(
        "file.write",
        "建立或覆寫 UTF-8 文字檔；完整差異須經使用者確認。",
        WriteFile,
        workspace.write,
    )

    def command(params: Command):
        if (
            any(not arg or len(arg) > 2000 or "\0" in arg for arg in params.argv)
            or sum(map(len, params.argv)) > 8000
        ):
            raise ValueError("指令參數為空或過長。")
        return PreparedTool(
            lambda: run_command(workspace.root, params.argv, params.timeout_seconds, cancelled),
            f"在無網路的 Python 容器執行，最多 {params.timeout_seconds} 秒。\n"
            f"程式可讀寫整個專用工作目錄：{workspace.root}\n"
            "完整 argv：" + json.dumps(params.argv, ensure_ascii=False),
        )

    registry.add(
        "command.run",
        "在已安裝的 python:3.12-slim Docker 容器執行 argv；無網路，僅能讀寫 /work，主機無 shell fallback。",
        Command,
        command,
    )
    return registry
