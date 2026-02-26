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

## 2026-02-26 - Batch 3: Feature Completeness + Concurrency + Coverage Expansion
- Reworked agent broadcaster background lifecycle to use explicit receive/send tasks, fixing TaskGroup cancellation issues on leave/reconnect.
- Added Blueprint per-node timeout support (`Blueprint.execute(timeout=...)`) with async handler coverage and timeout tests.
- Fixed `@shared` namespace behavior and added `synced(auto_commit=True)` capability with tests.
- Added namespace input type validation and tuple normalization in `Namespace.set()` with dedicated tests.
- Added EventLog retention controls (`max_entries`, `max_bytes`), compaction API (`compact(snapshot_bytes)`), and lock-protected read/write access.
- Added lock-based concurrency protections in `PeerManager` and `CRDTStore` internals.
- Hardened `E2BSandboxAdapter` with startup/runtime failure handling, pre-start guards, and new mock-based unit tests.
- Added integration test for two networked `PlutusAgent` instances through `SyncDaemon` verifying automatic bidirectional sync without manual imports.
- Added malformed input tests for envelope decode and VFS JSON ingest; expanded total tests from 44 to 61 passing.
- Updated `examples/networked_swarm.py` to use automatic real-time sync via `PlutusAgent.join()` and background broadcaster loops.

## 2026-02-26 - Batch 4: Verification Stabilization
- Fixed networked example convergence race by switching per-agent writes to `await agent.sync()` and adding post-join settle delay, preventing send-queue race conditions before leave.
- Re-ran full verification commands: `uv run pytest tests/ -v`, `uv run python examples/basic_swarm.py`, `uv run python examples/networked_swarm.py`, and `uv run python examples/blueprint_example.py`.

## 2026-02-26 - Batch 5: Repository Baseline Snapshot
- Added previously untracked scaffold files (package metadata, module export/init files, utility modules, and remaining examples) to leave the repository in a coherent committed state.

## 2026-02-26 - Batch 6: Graceful Leave Flush
- Added pending-update drain tracking in `DiffBroadcaster` and `flush_pending(timeout=...)`.
- Updated `PlutusAgent.leave()` to await pending broadcast queue drain before stopping loops and closing transport, reducing last-moment message drops.

## 2026-02-26 - Batch 7: OSS Packaging + Fast Onboarding (uv-first)
- Added open-source project fundamentals: `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`.
- Added release guide at `docs/RELEASING.md` with uv-based build/publish process and Trusted Publishing notes.
- Added GitHub collaboration/release automation:
  - `.github/workflows/ci.yml` (uv-based matrix test CI)
  - `.github/workflows/publish.yml` (Release-triggered PyPI publish)
  - issue templates and PR template for contributor onboarding.
- Expanded `pyproject.toml` package metadata (readme, license, classifiers, keywords, project URLs) for PyPI/open-source discoverability.
- Verified release packaging with `uv build` and kept contributor default checks fast (`pytest` required, lint/type optional).

## 2026-02-26 - Batch 8: PyPI Deployment Workflow Hardening
- Extended publish workflow to support both `testpypi` and `pypi` via `workflow_dispatch` input.
- Added release-tag/version guard in publish workflow to prevent publishing mismatched version tags.
- Added dedicated `testpypi` publish job/environment for release rehearsal.
- Updated release docs with exact Trusted Publishing fields and dry-run flow.

## 2026-02-26 - Batch 9: Distribution Rename for PyPI Availability
- Renamed package distribution from `plutus` to `plutus-sync` in `pyproject.toml`.
- Updated project URLs to the live GitHub repository (`RB9823/plutus`).
- Updated onboarding/release docs to use `plutus-sync` install commands while keeping import path `plutus`.
- Regenerated lock metadata and verified build artifacts now produce `plutus_sync-0.1.0` wheel/sdist names.
