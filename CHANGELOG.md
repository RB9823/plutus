# Plutus Change Log

## 2026-02-26 - Batch 1: Agent/Broadcaster Critical Runtime Wiring
- Started `DiffBroadcaster.receive_loop()` and new `send_loop()` in a persistent task group from `PlutusAgent.join()`.
- Added async lifecycle firing in `PlutusAgent.join()` and `leave()` via `LifecycleManager.fire_async()`.
- Wired shard dispatch from CRDT root change events in `PlutusAgent` by parsing map deltas and forwarding changed keys to `ShardManager`.
- Added incremental sync tracking in `PlutusAgent.sync()` using a stored `VersionVector` (`_last_synced_vv`) and `CRDTStore.clone_oplog_vv()`.
- Added local-update suppression path in `DiffBroadcaster` so manual `sync()` does not double-send the same commit when auto-broadcast is enabled.
- Implemented queued async local update broadcasting (`send_nowait` + `send_loop`) to satisfy the sync callback constraints of `subscribe_local_update`.
