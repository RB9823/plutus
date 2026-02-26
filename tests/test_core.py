"""Tests for core module: store, document, shard, decorators."""

import anyio
import pytest

from plutus.core.store import CRDTStore
from plutus.core.document import PlutusDoc
from plutus.core.shard import ShardManager
from plutus.core.types import Shard
from plutus.core.decorators import shared, synced


class TestCRDTStore:
    def test_basic_map_operations(self):
        store = CRDTStore()
        m = store.get_map("tasks")
        m.insert("task_1", "do stuff")
        store.commit()
        assert m.get_deep_value() == {"task_1": "do stuff"}

    def test_two_stores_converge(self):
        """Two stores export/import updates and converge."""
        store_a = CRDTStore(peer_id=1)
        store_b = CRDTStore(peer_id=2)

        # A writes
        ma = store_a.get_map("data")
        ma.insert("key_a", "value_a")
        store_a.commit()

        # B writes
        mb = store_b.get_map("data")
        mb.insert("key_b", "value_b")
        store_b.commit()

        # Sync A -> B
        updates_a = store_a.export_updates()
        store_b.import_updates(updates_a)

        # Sync B -> A
        updates_b = store_b.export_updates()
        store_a.import_updates(updates_b)

        # Both should have the same state
        assert store_a.get_deep_value() == store_b.get_deep_value()
        deep = store_a.get_deep_value()
        assert deep["data"]["key_a"] == "value_a"
        assert deep["data"]["key_b"] == "value_b"

    def test_snapshot_export_import(self):
        store_a = CRDTStore(peer_id=1)
        m = store_a.get_map("test")
        m.insert("x", 42)
        store_a.commit()

        snapshot = store_a.export_snapshot()

        store_b = CRDTStore(peer_id=2)
        store_b.import_updates(snapshot)
        assert store_b.get_map("test").get_deep_value() == {"x": 42}

    def test_counter(self):
        store = CRDTStore()
        c = store.get_counter("cnt")
        c.increment(5)
        c.increment(3)
        store.commit()
        assert c.value == 8.0

    def test_list(self):
        store = CRDTStore()
        items = store.get_list("items")
        items.insert(0, "a")
        items.insert(1, "b")
        store.commit()
        assert items.get_deep_value() == ["a", "b"]

    def test_text(self):
        store = CRDTStore()
        t = store.get_text("doc")
        t.insert(0, "hello world")
        store.commit()
        assert t.to_string() == "hello world"

    def test_on_local_update(self):
        store = CRDTStore()
        updates = []
        store.on_local_update(lambda b: (updates.append(b), True)[-1])
        m = store.get_map("test")
        m.insert("k", "v")
        store.commit()
        assert len(updates) == 1
        assert isinstance(updates[0], bytes)

    def test_on_change(self):
        store = CRDTStore()
        events = []
        store.on_change(lambda e: events.append(e))
        m = store.get_map("test")
        m.insert("k", "v")
        store.commit()
        assert len(events) == 1

    @pytest.mark.anyio
    async def test_concurrent_writes(self):
        store = CRDTStore()
        doc = PlutusDoc(store=store)
        ns = doc.namespace("tasks")

        async def writer(prefix: str):
            for i in range(10):
                ns.set(f"{prefix}_{i}", i)
                doc.commit()
                await anyio.sleep(0)

        async with anyio.create_task_group() as tg:
            tg.start_soon(writer, "a")
            tg.start_soon(writer, "b")

        values = doc.namespace("tasks").to_dict()
        assert len(values) == 20


class TestPlutusDoc:
    def test_namespace_crud(self):
        doc = PlutusDoc()
        ns = doc.namespace("tasks")
        ns.set("task_1", "plan")
        ns.set("task_2", "execute")
        doc.commit()

        assert ns.get("task_1") == "plan"
        assert ns.get("task_2") == "execute"
        assert "task_1" in ns
        assert len(ns) == 2
        assert set(ns.keys()) == {"task_1", "task_2"}

    def test_namespace_delete(self):
        doc = PlutusDoc()
        ns = doc.namespace("data")
        ns.set("key", "value")
        doc.commit()
        assert ns.get("key") == "value"
        ns.delete("key")
        doc.commit()

    def test_namespace_dict_access(self):
        doc = PlutusDoc()
        ns = doc.namespace("data")
        ns["x"] = 10
        doc.commit()
        assert ns["x"] == 10

    def test_namespace_to_dict(self):
        doc = PlutusDoc()
        ns = doc.namespace("config")
        ns.set("a", 1)
        ns.set("b", 2)
        doc.commit()
        assert ns.to_dict() == {"a": 1, "b": 2}

    def test_state_alias(self):
        doc = PlutusDoc()
        ns = doc.state("tasks")
        assert ns is doc.namespace("tasks")

    def test_multiple_namespaces(self):
        doc = PlutusDoc()
        tasks = doc.namespace("tasks")
        config = doc.namespace("config")
        tasks.set("t1", "do")
        config.set("timeout", 30)
        doc.commit()
        deep = doc.get_deep_value()
        assert deep["tasks"]["t1"] == "do"
        assert deep["config"]["timeout"] == 30


class TestShardManager:
    def test_shard_dispatch(self):
        mgr = ShardManager()
        received = []
        shard = Shard(name="tasks", prefixes=["task_"])
        mgr.register(shard, lambda k, v: received.append((k, v)))

        mgr.dispatch("task_1", "data")
        mgr.dispatch("config_x", "other")

        assert len(received) == 1
        assert received[0] == ("task_1", "data")

    def test_shard_no_prefix_matches_all(self):
        mgr = ShardManager()
        received = []
        shard = Shard(name="all")
        mgr.register(shard, lambda k, v: received.append((k, v)))

        mgr.dispatch("anything", "data")
        assert len(received) == 1

    def test_unregister(self):
        mgr = ShardManager()
        shard = Shard(name="test", prefixes=["t_"])
        mgr.register(shard, lambda k, v: None)
        assert "test" in mgr.shard_names
        mgr.unregister("test")
        assert "test" not in mgr.shard_names

    def test_multiple_shards(self):
        mgr = ShardManager()
        r1, r2 = [], []
        mgr.register(Shard("s1", ["a_"]), lambda k, v: r1.append(k))
        mgr.register(Shard("s2", ["b_"]), lambda k, v: r2.append(k))

        mgr.dispatch("a_key", 1)
        mgr.dispatch("b_key", 2)

        assert r1 == ["a_key"]
        assert r2 == ["b_key"]


class TestSyncedDescriptor:
    def test_synced_read_write(self):
        class Agent:
            task_count = synced(default=0)

            def __init__(self):
                self._plutus_doc = PlutusDoc()

        agent = Agent()
        assert agent.task_count == 0

        agent.task_count = 5
        agent._plutus_doc.commit()
        assert agent.task_count == 5

    def test_synced_auto_commit(self):
        class Agent:
            task_count = synced(default=0, auto_commit=True)

            def __init__(self):
                self._plutus_doc = PlutusDoc()

        agent = Agent()
        agent.task_count = 7
        assert agent.task_count == 7

    def test_shared_decorator_sets_namespace(self):
        @shared(ns="tasks")
        class Agent:
            task_count = synced(default=0)

            def __init__(self):
                self._plutus_doc = PlutusDoc()

        agent = Agent()
        agent.task_count = 3
        agent._plutus_doc.commit()

        assert agent._plutus_doc.namespace("tasks").get("task_count") == 3
        assert agent._plutus_doc.namespace("state").get("task_count") is None


class TestNamespaceValidation:
    def test_set_rejects_unsupported_types(self):
        doc = PlutusDoc()
        ns = doc.namespace("data")
        with pytest.raises(TypeError):
            ns.set("bad", object())

    def test_set_normalizes_tuples_to_lists(self):
        doc = PlutusDoc()
        ns = doc.namespace("data")
        ns.set("numbers", (1, 2, 3))
        doc.commit()
        assert ns.get("numbers") == [1, 2, 3]
