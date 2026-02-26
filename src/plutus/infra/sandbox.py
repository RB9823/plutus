"""SandboxAdapter ABC + LocalSandboxAdapter + E2BSandboxAdapter."""

from __future__ import annotations

import abc
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SandboxAdapter(abc.ABC):
    """Abstract adapter for running agents in sandboxed environments."""

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @abc.abstractmethod
    async def exec(self, command: str) -> str: ...

    @abc.abstractmethod
    async def write_file(self, path: str, content: str) -> None: ...

    @abc.abstractmethod
    async def read_file(self, path: str) -> str: ...


class LocalSandboxAdapter(SandboxAdapter):
    """Sandbox adapter that runs commands locally (no isolation)."""

    def __init__(self, working_dir: str = ".") -> None:
        self._working_dir = working_dir

    async def start(self) -> None:
        logger.debug("local sandbox start: cwd=%s", self._working_dir)

    async def stop(self) -> None:
        logger.debug("local sandbox stop: cwd=%s", self._working_dir)

    async def exec(self, command: str) -> str:
        import anyio
        result = await anyio.run_process(
            command, shell=True, cwd=self._working_dir
        )
        return result.stdout.decode()

    async def write_file(self, path: str, content: str) -> None:
        from pathlib import Path
        (Path(self._working_dir) / path).write_text(content)

    async def read_file(self, path: str) -> str:
        from pathlib import Path
        return (Path(self._working_dir) / path).read_text()


class E2BSandboxAdapter(SandboxAdapter):
    """Sandbox adapter for E2B cloud sandboxes."""

    def __init__(self, template: str = "base", api_key: str | None = None) -> None:
        self._template = template
        self._api_key = api_key
        self._sandbox: Any = None

    async def start(self) -> None:
        try:
            from e2b import AsyncSandbox
        except ImportError:
            raise ImportError("e2b package required: pip install plutus[e2b]")
        kwargs: dict[str, Any] = {"template": self._template}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        try:
            self._sandbox = await AsyncSandbox.create(**kwargs)
        except Exception as exc:
            logger.exception("failed to start E2B sandbox")
            raise RuntimeError("failed to start E2B sandbox") from exc

    async def stop(self) -> None:
        if self._sandbox:
            try:
                await self._sandbox.kill()
            except Exception as exc:
                logger.exception("failed to stop E2B sandbox")
                raise RuntimeError("failed to stop E2B sandbox") from exc
            finally:
                self._sandbox = None

    async def exec(self, command: str) -> str:
        if self._sandbox is None:
            raise RuntimeError("sandbox not started")
        try:
            result = await self._sandbox.commands.run(command)
        except Exception as exc:
            logger.exception("E2B command failed: %s", command)
            raise RuntimeError("sandbox command execution failed") from exc
        return result.stdout

    async def write_file(self, path: str, content: str) -> None:
        if self._sandbox is None:
            raise RuntimeError("sandbox not started")
        try:
            await self._sandbox.files.write(path, content)
        except Exception as exc:
            logger.exception("E2B write_file failed: %s", path)
            raise RuntimeError("sandbox write_file failed") from exc

    async def read_file(self, path: str) -> str:
        if self._sandbox is None:
            raise RuntimeError("sandbox not started")
        try:
            return await self._sandbox.files.read(path)
        except Exception as exc:
            logger.exception("E2B read_file failed: %s", path)
            raise RuntimeError("sandbox read_file failed") from exc
