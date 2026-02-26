"""Tests for infrastructure module: vfs, daemon."""

import json
import socket
import sys
import tempfile
import types
from pathlib import Path

import anyio
import pytest

from plutus import PlutusAgent
from plutus.core.store import CRDTStore
from plutus.infra.daemon import SyncDaemon
from plutus.infra.sandbox import E2BSandboxAdapter
from plutus.infra.vfs import VirtualFilesystem


class TestVirtualFilesystem:
    def test_sync_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CRDTStore()
            m = store.get_map("tasks")
            m.insert("task_1", "plan")
            m.insert("task_2", "execute")
            store.commit()

            vfs = VirtualFilesystem(store, tmpdir)
            vfs.sync_to_disk()

            tasks_file = Path(tmpdir) / "tasks.json"
            assert tasks_file.exists()
            data = json.loads(tasks_file.read_text())
            assert data == {"task_1": "plan", "task_2": "execute"}

    def test_sync_from_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write JSON file
            tasks_file = Path(tmpdir) / "config.json"
            tasks_file.write_text(json.dumps({"timeout": 30, "retries": 3}))

            store = CRDTStore()
            vfs = VirtualFilesystem(store, tmpdir)
            vfs.sync_from_disk()

            m = store.get_map("config")
            assert m.get_deep_value() == {"timeout": 30, "retries": 3}

    def test_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_a = CRDTStore(peer_id=1)
            m = store_a.get_map("data")
            m.insert("key", "value")
            store_a.commit()

            vfs_a = VirtualFilesystem(store_a, tmpdir)
            snap_path = vfs_a.write_snapshot()

            store_b = CRDTStore(peer_id=2)
            vfs_b = VirtualFilesystem(store_b, tmpdir)
            vfs_b.load_snapshot(snap_path)

            assert store_b.get_map("data").get_deep_value() == {"key": "value"}

    def test_sync_from_disk_malformed_json_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.json"
            bad_file.write_text("{invalid json")
            store = CRDTStore()
            vfs = VirtualFilesystem(store, tmpdir)
            vfs.sync_from_disk()
            assert store.get_deep_value() == {}


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestSyncDaemonIntegration:
    @pytest.mark.anyio
    async def test_agents_auto_sync_without_manual_import(self):
        port = _free_port()
        daemon = SyncDaemon(port=port)
        await daemon.start()

        agent_a = PlutusAgent(name="a", peer_id=101)
        agent_b = PlutusAgent(name="b", peer_id=202)
        uri = f"ws://localhost:{port}"

        try:
            await agent_a.join(server_uri=uri)
            await agent_b.join(server_uri=uri)

            agent_a.state("shared").set("from_a", "hello")
            agent_a.commit()

            with anyio.fail_after(2):
                while agent_b.state("shared").get("from_a") != "hello":
                    await anyio.sleep(0.05)

            agent_b.state("shared").set("from_b", "world")
            agent_b.commit()
            with anyio.fail_after(2):
                while agent_a.state("shared").get("from_b") != "world":
                    await anyio.sleep(0.05)
        finally:
            await agent_a.leave()
            await agent_b.leave()
            await daemon.stop()


class TestE2BSandboxAdapter:
    @pytest.mark.anyio
    async def test_exec_requires_start(self):
        adapter = E2BSandboxAdapter()
        with pytest.raises(RuntimeError):
            await adapter.exec("echo hi")

    @pytest.mark.anyio
    async def test_happy_path_with_mocked_e2b(self, monkeypatch):
        class FakeResult:
            stdout = "ok"

        class FakeCommands:
            async def run(self, command):
                assert command == "pwd"
                return FakeResult()

        class FakeFiles:
            async def write(self, path, content):
                assert path == "/tmp/test.txt"
                assert content == "data"

            async def read(self, path):
                assert path == "/tmp/test.txt"
                return "data"

        class FakeSandbox:
            def __init__(self):
                self.commands = FakeCommands()
                self.files = FakeFiles()
                self.killed = False

            async def kill(self):
                self.killed = True

        class FakeAsyncSandbox:
            @staticmethod
            async def create(**kwargs):
                assert kwargs["template"] == "base"
                return FakeSandbox()

        monkeypatch.setitem(sys.modules, "e2b", types.SimpleNamespace(AsyncSandbox=FakeAsyncSandbox))

        adapter = E2BSandboxAdapter(template="base")
        await adapter.start()
        output = await adapter.exec("pwd")
        assert output == "ok"
        await adapter.write_file("/tmp/test.txt", "data")
        assert await adapter.read_file("/tmp/test.txt") == "data"
        await adapter.stop()

    @pytest.mark.anyio
    async def test_start_failure_raises_runtime_error(self, monkeypatch):
        class FailingAsyncSandbox:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("boom")

        monkeypatch.setitem(sys.modules, "e2b", types.SimpleNamespace(AsyncSandbox=FailingAsyncSandbox))

        adapter = E2BSandboxAdapter()
        with pytest.raises(RuntimeError):
            await adapter.start()
