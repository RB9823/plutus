"""VirtualFilesystem — syncs CRDT state to/from JSON files on disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from plutus.core.store import CRDTStore

logger = logging.getLogger(__name__)


class VirtualFilesystem:
    """Maps CRDT document state to JSON files in a directory, and vice versa.

    Each top-level key in the CRDT doc becomes a JSON file:
        state/<key>.json
    """

    def __init__(self, store: CRDTStore, base_dir: str | Path) -> None:
        self._store = store
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def sync_to_disk(self) -> None:
        """Write current CRDT state to JSON files."""
        state = self._store.get_deep_value()
        for key, value in state.items():
            path = self._base_dir / f"{key}.json"
            path.write_text(json.dumps(value, indent=2, default=str))

    def sync_from_disk(self) -> None:
        """Read JSON files and write them into the CRDT store."""
        for path in self._base_dir.glob("*.json"):
            key = path.stem
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                logger.warning("skipping malformed JSON file: %s", path)
                continue
            except Exception:
                logger.exception("failed to read JSON file: %s", path)
                continue
            if isinstance(data, dict):
                m = self._store.get_map(key)
                for k, v in data.items():
                    try:
                        m.insert(k, v)
                    except Exception:
                        logger.exception("failed to import key %s from %s", k, path)
            else:
                logger.warning("skipping non-object JSON root in file: %s", path)
        self._store.commit()

    def write_snapshot(self, path: str | Path | None = None) -> Path:
        """Write a binary CRDT snapshot to disk."""
        snapshot_path = Path(path) if path else self._base_dir / "snapshot.bin"
        snapshot_path.write_bytes(self._store.export_snapshot())
        return snapshot_path

    def load_snapshot(self, path: str | Path | None = None) -> None:
        """Load a binary CRDT snapshot from disk."""
        snapshot_path = Path(path) if path else self._base_dir / "snapshot.bin"
        self._store.import_updates(snapshot_path.read_bytes())
