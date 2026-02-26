"""Tests for network module: transport, event_log, broadcaster, peer."""

import tempfile
from pathlib import Path

import pytest

from plutus.net.transport import Envelope, MessageType
from plutus.net.event_log import EventLog
from plutus.net.peer import PeerManager
from plutus.core.store import CRDTStore
from plutus.net.broadcaster import DiffBroadcaster


class TestEnvelope:
    def test_roundtrip(self):
        env = Envelope(
            msg_type=MessageType.CRDT_UPDATE,
            sender=12345,
            target=None,
            payload=b"hello world",
        )
        encoded = env.encode()
        decoded = Envelope.decode(encoded)

        assert decoded.msg_type == MessageType.CRDT_UPDATE
        assert decoded.sender == 12345
        assert decoded.target is None
        assert decoded.payload == b"hello world"

    def test_roundtrip_with_target(self):
        env = Envelope(
            msg_type=MessageType.HEARTBEAT,
            sender=1,
            target=2,
            payload=b"",
        )
        decoded = Envelope.decode(env.encode())
        assert decoded.target == 2
        assert decoded.msg_type == MessageType.HEARTBEAT

    def test_all_message_types(self):
        for mt in MessageType:
            env = Envelope(msg_type=mt, sender=0, target=None, payload=b"")
            decoded = Envelope.decode(env.encode())
            assert decoded.msg_type == mt

    def test_decode_rejects_malformed_payload(self):
        with pytest.raises(ValueError):
            Envelope.decode(b"not-msgpack")

    def test_decode_rejects_missing_fields(self):
        from plutus._util.serialization import pack

        with pytest.raises(ValueError):
            Envelope.decode(pack({"t": 1}))


class TestEventLog:
    def test_append_and_replay(self):
        log = EventLog()
        log.append(b"entry1")
        log.append(b"entry2")
        log.append(b"entry3")

        entries = list(log.replay())
        assert len(entries) == 3
        assert entries[0] == b"entry1"
        assert entries[2] == b"entry3"

    def test_len_and_getitem(self):
        log = EventLog()
        log.append(b"a")
        log.append(b"b")
        assert len(log) == 2
        assert log[0] == b"a"
        assert log[1] == b"b"

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "log.bin"
            log1 = EventLog(path)
            log1.append(b"data1")
            log1.append(b"data2")

            log2 = EventLog(path)
            entries = list(log2.replay())
            assert len(entries) == 2
            assert entries[0] == b"data1"
            assert entries[1] == b"data2"

    def test_retention_max_entries(self):
        log = EventLog(max_entries=2)
        log.append(b"a")
        log.append(b"b")
        log.append(b"c")
        assert list(log.replay()) == [b"b", b"c"]

    def test_compact_clears_history(self):
        log = EventLog()
        log.append(b"one")
        log.append(b"two")
        log.compact(b"snapshot")
        assert list(log.replay()) == []


class TestPeerManager:
    def test_add_remove_peer(self):
        mgr = PeerManager()
        mgr.add_peer(1)
        mgr.add_peer(2)
        assert mgr.peer_count == 2
        assert set(mgr.peer_ids) == {1, 2}

        mgr.remove_peer(1)
        assert mgr.peer_count == 1

    def test_heartbeat(self):
        mgr = PeerManager(heartbeat_timeout=0.001)
        mgr.add_peer(1)
        import time
        time.sleep(0.01)
        stale = mgr.stale_peers()
        assert 1 in stale

    def test_prune_stale(self):
        mgr = PeerManager(heartbeat_timeout=0.001)
        mgr.add_peer(1)
        import time
        time.sleep(0.01)
        pruned = mgr.prune_stale()
        assert 1 in pruned
        assert mgr.peer_count == 0

    def test_peer_metadata(self):
        mgr = PeerManager()
        info = mgr.add_peer(1, metadata={"name": "agent_1"})
        assert info.metadata["name"] == "agent_1"
        assert mgr.get_peer(1).metadata["name"] == "agent_1"


class TestBroadcasterSync:
    def test_two_stores_sync_via_event_log(self):
        """Two stores sync through a shared event log."""
        store_a = CRDTStore(peer_id=1)
        store_b = CRDTStore(peer_id=2)
        log = EventLog()

        broadcaster_a = DiffBroadcaster(store=store_a, event_log=log)
        broadcaster_a.start_local_subscription()

        # A writes
        m = store_a.get_map("data")
        m.insert("from_a", "hello")
        store_a.commit()

        # B replays the log
        assert len(log) == 1
        entry = log[0]
        envelope = Envelope.decode(entry)
        assert envelope.msg_type == MessageType.CRDT_UPDATE
        store_b.import_updates(envelope.payload)

        assert store_b.get_map("data").get_deep_value() == {"from_a": "hello"}
