"""CRDTStore — wraps LoroDoc for conflict-free state management."""

from __future__ import annotations

from typing import Any, Callable

from loro import ExportMode, LoroCounter, LoroDoc, LoroList, LoroMap, LoroText, VersionVector


class CRDTStore:
    """Wraps a LoroDoc to provide a simplified CRDT state interface."""

    def __init__(self, peer_id: int | None = None) -> None:
        self._doc = LoroDoc()
        if peer_id is not None:
            self._doc.peer_id = peer_id
        self._local_update_sub: Any = None
        self._root_sub: Any = None

    @property
    def doc(self) -> LoroDoc:
        return self._doc

    @property
    def peer_id(self) -> int:
        return self._doc.peer_id

    def clone_oplog_vv(self) -> VersionVector:
        """Return a copy of the current oplog version vector."""
        return VersionVector.decode(self._doc.oplog_vv.encode())

    def get_map(self, key: str) -> LoroMap:
        return self._doc.get_map(key)

    def get_list(self, key: str) -> LoroList:
        return self._doc.get_list(key)

    def get_text(self, key: str) -> LoroText:
        return self._doc.get_text(key)

    def get_counter(self, key: str) -> LoroCounter:
        return self._doc.get_counter(key)

    def commit(self) -> None:
        self._doc.commit()

    def export_snapshot(self) -> bytes:
        return self._doc.export(ExportMode.Snapshot())

    def export_updates(self, since: VersionVector | None = None) -> bytes:
        if since is None:
            since = VersionVector()
        return self._doc.export(ExportMode.Updates(since))

    def import_updates(self, data: bytes) -> None:
        self._doc.import_batch([data])

    def import_batch(self, updates: list[bytes]) -> None:
        self._doc.import_batch(updates)

    def on_local_update(self, callback: Callable[[bytes], bool]) -> None:
        """Subscribe to local updates. Callback receives raw update bytes and must return bool."""
        self._local_update_sub = self._doc.subscribe_local_update(callback)

    def on_change(self, callback: Callable[[Any], None]) -> None:
        """Subscribe to all changes (local and remote)."""
        self._root_sub = self._doc.subscribe_root(callback)

    def get_deep_value(self) -> dict[str, Any]:
        return self._doc.get_deep_value()
