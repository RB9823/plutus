# Plutus Change Log

## 2026-02-26 - Batch 1: Agent/Broadcaster Critical Runtime Wiring
- Started `DiffBroadcaster.receive_loop()` and new `send_loop()` in a persistent task group from `PlutusAgent.join()`.
- Added async lifecycle firing in `PlutusAgent.join()` and `leave()` via `LifecycleManager.fire_async()`.
- Wired shard dispatch from CRDT root change events in `PlutusAgent` by parsing map deltas and forwarding changed keys to `ShardManager`.
- Added incremental sync tracking in `PlutusAgent.sync()` using a stored `VersionVector` (`_last_synced_vv`) and `CRDTStore.clone_oplog_vv()`.
- Added local-update suppression path in `DiffBroadcaster` so manual `sync()` does not double-send the same commit when auto-broadcast is enabled.
- Implemented queued async local update broadcasting (`send_nowait` + `send_loop`) to satisfy the sync callback constraints of `subscribe_local_update`.

## 2026-02-26 - Batch 2: Transport + Infra Hardening
- Added envelope wire versioning (`version=1`) and strict `Envelope.decode()` validation for malformed msgpack, missing fields, bad types, and invalid message types.
- Extended `Transport` with `is_connected` and upgraded `WebSocketTransport` with retry/backoff connect behavior, reconnect support, connection-state checks, and clearer connection-closed errors.
- Added optional token auth + peer identity handshake to `WebSocketServer` (`Authorization` + `X-Plutus-Peer-Id`) and enforced sender verification for authenticated sessions.
- Added WebSocket max message size configuration (10MB default) to both client connect and server serve paths.
- Hardened server client tracking with lock-protected client map access and safer close handling during shutdown.
- Added agent-side auto-reconnect support path (`auto_reconnect=True`), including sync-time reconnect attempts and broadcaster task restarts.
- Added input hardening and logging for daemon update imports and VFS JSON ingest (`sync_from_disk`) error handling.
- Added namespace value validation in `Namespace.set()` to reject unsupported CRDT value types early.
