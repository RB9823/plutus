"""PeerManager — tracks connections, heartbeats, and partition detection."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    peer_id: int
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class PeerManager:
    """Tracks connected peers and detects partitions via heartbeat timeouts."""

    def __init__(self, heartbeat_timeout: float = 30.0) -> None:
        self._peers: dict[int, PeerInfo] = {}
        self._heartbeat_timeout = heartbeat_timeout
        self._lock = RLock()

    def add_peer(self, peer_id: int, metadata: dict[str, Any] | None = None) -> PeerInfo:
        with self._lock:
            info = PeerInfo(peer_id=peer_id, metadata=metadata or {})
            self._peers[peer_id] = info
            return info

    def remove_peer(self, peer_id: int) -> None:
        with self._lock:
            self._peers.pop(peer_id, None)

    def record_heartbeat(self, peer_id: int) -> None:
        with self._lock:
            if peer_id in self._peers:
                self._peers[peer_id].last_heartbeat = time.time()
            else:
                logger.debug("heartbeat from unknown peer %s", peer_id)

    def get_peer(self, peer_id: int) -> PeerInfo | None:
        with self._lock:
            return self._peers.get(peer_id)

    @property
    def peer_ids(self) -> list[int]:
        with self._lock:
            return list(self._peers.keys())

    @property
    def peer_count(self) -> int:
        with self._lock:
            return len(self._peers)

    def stale_peers(self) -> list[int]:
        """Return peer IDs that haven't sent a heartbeat within the timeout."""
        now = time.time()
        with self._lock:
            return [
                pid
                for pid, info in self._peers.items()
                if now - info.last_heartbeat > self._heartbeat_timeout
            ]

    def prune_stale(self) -> list[int]:
        """Remove and return stale peers."""
        with self._lock:
            now = time.time()
            stale = [
                pid
                for pid, info in self._peers.items()
                if now - info.last_heartbeat > self._heartbeat_timeout
            ]
            for pid in stale:
                self._peers.pop(pid, None)
            return stale
