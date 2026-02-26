"""DiffBroadcaster — bridges local CRDT updates to the network and vice versa."""

from __future__ import annotations

import logging
from threading import Lock

import anyio

from plutus.core.store import CRDTStore
from plutus.net.event_log import EventLog
from plutus.net.transport import Envelope, MessageType, Transport

logger = logging.getLogger(__name__)


class DiffBroadcaster:
    """Subscribes to local CRDT updates, broadcasts them via transport,
    and imports received remote updates into the local store."""

    def __init__(
        self,
        store: CRDTStore,
        transport: Transport | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        self._store = store
        self._transport = transport
        self._event_log = event_log
        self._running = False
        self._local_update_cb = None
        self._suppress_local_updates = 0
        self._pending_send, self._pending_recv = anyio.create_memory_object_stream[bytes](1024)
        self._pending_lock = Lock()
        self._pending_count = 0
        self._pending_drained = anyio.Event()
        self._pending_drained.set()

    def bind_transport(self, transport: Transport) -> None:
        self._transport = transport

    def suppress_next_local_update(self) -> None:
        """Skip one local update callback (used when sync() sends manually)."""
        self._suppress_local_updates += 1

    def _on_local_update(self, update_bytes: bytes) -> bool:
        if self._suppress_local_updates > 0:
            self._suppress_local_updates -= 1
            return True

        if self._transport is None:
            if self._event_log is not None:
                envelope = Envelope(
                    msg_type=MessageType.CRDT_UPDATE,
                    sender=self._store.peer_id,
                    target=None,
                    payload=update_bytes,
                )
                self._event_log.append(envelope.encode())
            return True

        try:
            self._pending_send.send_nowait(update_bytes)
            with self._pending_lock:
                if self._pending_count == 0:
                    self._pending_drained = anyio.Event()
                self._pending_count += 1
        except anyio.WouldBlock:
            logger.warning("dropping local CRDT update because broadcaster queue is full")
        except (anyio.ClosedResourceError, anyio.BrokenResourceError):
            logger.debug("ignoring local update because broadcaster queue is closed")
        return True

    def start_local_subscription(self) -> None:
        """Subscribe to local updates and enqueue them for async broadcast."""
        self._local_update_cb = self._on_local_update
        self._store.on_local_update(self._local_update_cb)

    async def broadcast_update(self, update_bytes: bytes) -> None:
        """Broadcast an update to the transport and append it to the event log."""
        if not self._transport:
            return
        envelope = Envelope(
            msg_type=MessageType.CRDT_UPDATE,
            sender=self._store.peer_id,
            target=None,
            payload=update_bytes,
        )
        if self._event_log is not None:
            self._event_log.append(envelope.encode())
        await self._transport.send(envelope)

    async def send_loop(self, task_status: anyio.abc.TaskStatus = anyio.TASK_STATUS_IGNORED) -> None:
        """Continuously send locally queued updates over the transport."""
        self._running = True
        task_status.started()
        try:
            while self._running:
                try:
                    update_bytes = await self._pending_recv.receive()
                except anyio.EndOfStream:
                    break
                if not self._running:
                    break
                try:
                    await self.broadcast_update(update_bytes)
                except Exception:
                    logger.exception("failed to send CRDT update")
                    break
                finally:
                    with self._pending_lock:
                        if self._pending_count > 0:
                            self._pending_count -= 1
                        if self._pending_count == 0:
                            self._pending_drained.set()
        finally:
            self._running = False

    async def receive_loop(self, task_status: anyio.abc.TaskStatus = anyio.TASK_STATUS_IGNORED) -> None:
        """Continuously receive remote updates and import them."""
        if self._transport is None:
            task_status.started()
            return

        self._running = True
        task_status.started()
        try:
            while self._running:
                try:
                    envelope = await self._transport.receive()
                except Exception:
                    logger.exception("receive loop hit transport error")
                    reconnect = getattr(self._transport, "reconnect", None)
                    if reconnect is None:
                        break
                    try:
                        await reconnect()
                    except Exception:
                        logger.exception("receive loop reconnect failed")
                        break
                    continue
                if envelope.msg_type == MessageType.CRDT_UPDATE:
                    self._store.import_updates(envelope.payload)
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
        with self._pending_lock:
            self._pending_count = 0
            self._pending_drained.set()
        self._pending_send.close()

    async def flush_pending(self, timeout: float | None = None) -> bool:
        """Wait until queued local updates are drained by send_loop."""
        if timeout is None:
            await self._pending_drained.wait()
            return True
        with anyio.move_on_after(timeout) as scope:
            await self._pending_drained.wait()
        return not scope.cancel_called

    def replay_log(self) -> None:
        """Import all entries from the event log into the store."""
        if not self._event_log:
            return
        for entry in self._event_log.replay():
            try:
                envelope = Envelope.decode(entry)
            except ValueError:
                logger.warning("skipping malformed event log entry during replay")
                continue
            if envelope.sender != self._store.peer_id:
                self._store.import_updates(envelope.payload)
