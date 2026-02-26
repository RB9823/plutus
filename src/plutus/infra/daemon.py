"""SyncDaemon — WebSocket hub composing CRDTStore + Transport + Broadcaster + EventLog."""

from __future__ import annotations

import logging
from typing import Any

import anyio

from plutus.core.store import CRDTStore
from plutus.net.broadcaster import DiffBroadcaster
from plutus.net.event_log import EventLog
from plutus.net.peer import PeerManager
from plutus.net.transport import (
    Envelope,
    MessageType,
    WebSocketServer,
)

logger = logging.getLogger(__name__)


class SyncDaemon:
    """Central WebSocket hub that manages shared CRDT state for agent sandboxes.

    Composes CRDTStore + WebSocketServer + DiffBroadcaster + EventLog + PeerManager.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        event_log_path: str | None = None,
        *,
        auth_token: str | None = None,
        max_message_size: int | None = 10 * 1024 * 1024,
    ) -> None:
        self._store = CRDTStore()
        self._server = WebSocketServer(
            host=host,
            port=port,
            auth_token=auth_token,
            max_size=max_message_size,
        )
        self._event_log = EventLog(event_log_path)
        self._broadcaster = DiffBroadcaster(
            store=self._store,
            event_log=self._event_log,
        )
        self._peers = PeerManager()
        self._server.on_message(self._handle_message)

    @property
    def store(self) -> CRDTStore:
        return self._store

    @property
    def peers(self) -> PeerManager:
        return self._peers

    @property
    def event_log(self) -> EventLog:
        return self._event_log

    def _handle_message(self, envelope: Envelope) -> None:
        if envelope.msg_type == MessageType.JOIN:
            self._peers.add_peer(envelope.sender)
            logger.info("peer joined: %s", envelope.sender)
        elif envelope.msg_type == MessageType.LEAVE:
            self._peers.remove_peer(envelope.sender)
            logger.info("peer left: %s", envelope.sender)
        elif envelope.msg_type == MessageType.HEARTBEAT:
            self._peers.record_heartbeat(envelope.sender)
        elif envelope.msg_type == MessageType.CRDT_UPDATE:
            try:
                self._store.import_updates(envelope.payload)
                self._event_log.append(envelope.encode())
            except Exception:
                logger.exception("failed to import CRDT update from sender=%s", envelope.sender)

    async def start(self) -> None:
        self._broadcaster.start_local_subscription()
        await self._server.start()
        logger.info("sync daemon started")

    async def stop(self) -> None:
        self._broadcaster.stop()
        await self._server.stop()
        logger.info("sync daemon stopped")

    async def run_forever(self) -> None:
        await self.start()
        try:
            await anyio.sleep_forever()
        finally:
            await self.stop()
