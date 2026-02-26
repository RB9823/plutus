"""PlutusAgent — primary user-facing class composing all Plutus components."""

from __future__ import annotations

import logging
from typing import Any

import anyio
from loro import VersionVector

from plutus.core.document import Namespace, PlutusDoc
from plutus.core.shard import ShardManager
from plutus.core.types import Shard
from plutus.net.broadcaster import DiffBroadcaster
from plutus.net.transport import (
    Envelope,
    MessageType,
    Transport,
    WebSocketTransport,
)
from plutus.api.lifecycle import LifecycleEvent, LifecycleManager

logger = logging.getLogger(__name__)


class PlutusAgent:
    """Primary user-facing class for Plutus agents.

    Composes PlutusDoc + Transport + DiffBroadcaster + LifecycleManager.
    """

    def __init__(
        self,
        name: str,
        peer_id: int | None = None,
        doc: PlutusDoc | None = None,
        *,
        auto_reconnect: bool = True,
    ) -> None:
        self.name = name
        self._plutus_doc = doc or PlutusDoc(peer_id=peer_id)
        self._transport: Transport | None = None
        self._broadcaster: DiffBroadcaster | None = None
        self._lifecycle = LifecycleManager()
        self._shards = ShardManager()
        self._joined = False
        self._task_group: anyio.abc.TaskGroup | None = None
        self._last_synced_vv: VersionVector = self._plutus_doc.store.clone_oplog_vv()
        self._server_uri: str | None = None
        self._auth_token: str | None = None
        self._auto_reconnect = auto_reconnect

    @property
    def peer_id(self) -> int:
        return self._plutus_doc.peer_id

    @property
    def doc(self) -> PlutusDoc:
        return self._plutus_doc

    @property
    def lifecycle(self) -> LifecycleManager:
        return self._lifecycle

    @property
    def shards(self) -> ShardManager:
        return self._shards

    @property
    def is_joined(self) -> bool:
        return self._joined

    def state(self, name: str = "state") -> Namespace:
        return self._plutus_doc.namespace(name)

    def register_shard(self, shard: Shard, callback: Any) -> None:
        self._shards.register(shard, callback)

    @staticmethod
    def _vv_equal(a: VersionVector, b: VersionVector) -> bool:
        return a.includes_vv(b) and b.includes_vv(a)

    def _dispatch_changed_shards(self, diff_event: Any) -> None:
        for event in getattr(diff_event, "events", []):
            delta = getattr(getattr(event, "diff", None), "diff", None)
            updated = getattr(delta, "updated", None)
            if not isinstance(updated, dict):
                continue
            for key, value_or_container in updated.items():
                value = getattr(value_or_container, "value", value_or_container)
                self._shards.dispatch(str(key), value)

    def _on_store_change(self, diff_event: Any) -> None:
        self._dispatch_changed_shards(diff_event)
        self._lifecycle.fire(LifecycleEvent.ON_STATE_CHANGE, self, diff_event)

    async def _start_broadcaster_tasks(self) -> None:
        if self._task_group is not None or self._broadcaster is None:
            return
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        await self._task_group.start(self._broadcaster.receive_loop)
        await self._task_group.start(self._broadcaster.send_loop)

    async def _stop_broadcaster_tasks(self) -> None:
        if self._task_group is None:
            return
        self._task_group.cancel_scope.cancel()
        await self._task_group.__aexit__(None, None, None)
        self._task_group = None

    async def _reconnect_transport(self) -> bool:
        if not self._auto_reconnect or self._server_uri is None:
            return False

        logger.info("attempting transport reconnect for agent %s", self.name)
        await self._stop_broadcaster_tasks()
        if self._transport:
            try:
                await self._transport.close()
            except Exception:
                logger.debug("transport close failed during reconnect", exc_info=True)

        self._transport = await WebSocketTransport.connect(
            self._server_uri,
            peer_id=self.peer_id,
            token=self._auth_token,
        )
        if self._broadcaster is None:
            self._broadcaster = DiffBroadcaster(
                store=self._plutus_doc.store,
                transport=self._transport,
            )
            self._broadcaster.start_local_subscription()
        else:
            self._broadcaster.bind_transport(self._transport)

        await self._start_broadcaster_tasks()

        join_envelope = Envelope(
            msg_type=MessageType.JOIN,
            sender=self.peer_id,
            target=None,
            payload=b"",
        )
        await self._transport.send(join_envelope)
        self._last_synced_vv = self._plutus_doc.store.clone_oplog_vv()
        logger.info("transport reconnect completed for agent %s", self.name)
        return True

    async def join(self, server_uri: str | None = None, *, auth_token: str | None = None) -> None:
        """Join the swarm, optionally connecting to a sync server."""
        await self._lifecycle.fire_async(LifecycleEvent.BEFORE_JOIN, self)
        self._plutus_doc.store.on_change(self._on_store_change)

        if server_uri:
            self._server_uri = server_uri
            self._auth_token = auth_token
            self._transport = await WebSocketTransport.connect(
                server_uri,
                peer_id=self.peer_id,
                token=auth_token,
            )
            self._broadcaster = DiffBroadcaster(
                store=self._plutus_doc.store,
                transport=self._transport,
            )
            self._broadcaster.start_local_subscription()
            await self._start_broadcaster_tasks()
            # Send join envelope
            join_envelope = Envelope(
                msg_type=MessageType.JOIN,
                sender=self.peer_id,
                target=None,
                payload=b"",
            )
            await self._transport.send(join_envelope)
            self._last_synced_vv = self._plutus_doc.store.clone_oplog_vv()

        self._joined = True
        await self._lifecycle.fire_async(LifecycleEvent.AFTER_JOIN, self)

    async def leave(self) -> None:
        """Leave the swarm and disconnect."""
        await self._lifecycle.fire_async(LifecycleEvent.BEFORE_LEAVE, self)

        if self._transport:
            leave_envelope = Envelope(
                msg_type=MessageType.LEAVE,
                sender=self.peer_id,
                target=None,
                payload=b"",
            )
            try:
                await self._transport.send(leave_envelope)
            except Exception:
                pass
            if self._broadcaster:
                self._broadcaster.stop()
            await self._stop_broadcaster_tasks()
            await self._transport.close()
            self._transport = None
            self._broadcaster = None

        self._joined = False
        await self._lifecycle.fire_async(LifecycleEvent.AFTER_LEAVE, self)

    async def sync(self) -> None:
        """Commit local changes and broadcast to peers."""
        if self._broadcaster and self._transport:
            self._broadcaster.suppress_next_local_update()
        self._plutus_doc.commit()

        if self._broadcaster and self._transport:
            if not self._transport.is_connected:
                await self._reconnect_transport()

            current_vv = self._plutus_doc.store.clone_oplog_vv()
            if self._vv_equal(current_vv, self._last_synced_vv):
                return
            updates = self._plutus_doc.store.export_updates(since=self._last_synced_vv)
            try:
                await self._broadcaster.broadcast_update(updates)
            except Exception:
                if not await self._reconnect_transport():
                    raise
                await self._broadcaster.broadcast_update(updates)
            self._last_synced_vv = current_vv

    def commit(self) -> None:
        """Commit local changes (broadcasts automatically when connected)."""
        self._plutus_doc.commit()

    def on(self, event: LifecycleEvent, hook: Any) -> None:
        self._lifecycle.on(event, hook)

    async def complete(self) -> None:
        """Mark agent as complete and leave the swarm."""
        await self.leave()
