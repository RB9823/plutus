"""EventLog — append-only durable log for CRDT updates."""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from threading import RLock
from typing import Iterator

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only log storing length-prefixed binary entries.

    Wire format: [4-byte big-endian length][payload bytes]
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_entries: int | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self._path = Path(path) if path else None
        self._lock = RLock()
        self._entries: list[bytes] = []
        self._total_bytes = 0
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        data = self._path.read_bytes()
        offset = 0
        while offset < len(data):
            if offset + 4 > len(data):
                break
            length = struct.unpack("!I", data[offset : offset + 4])[0]
            offset += 4
            if offset + length > len(data):
                break
            entry = data[offset : offset + length]
            self._entries.append(entry)
            self._total_bytes += len(entry)
            offset += length

    def append(self, entry: bytes) -> None:
        with self._lock:
            self._entries.append(entry)
            self._total_bytes += len(entry)
            self._enforce_limits()
            if self._path:
                # When retention dropped old entries, rewrite the whole log.
                if self._should_rewrite:
                    self._rewrite_file()
                else:
                    with self._path.open("ab") as f:
                        f.write(struct.pack("!I", len(entry)))
                        f.write(entry)

    def replay(self) -> Iterator[bytes]:
        with self._lock:
            yield from list(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __getitem__(self, index: int) -> bytes:
        with self._lock:
            return self._entries[index]

    def compact(self, snapshot_bytes: bytes) -> None:
        """Drop historical entries after a snapshot is persisted elsewhere."""
        with self._lock:
            if not snapshot_bytes:
                logger.warning("compacting event log with empty snapshot payload")
            self._entries.clear()
            self._total_bytes = 0
            self._rewrite_file()

    @property
    def _should_rewrite(self) -> bool:
        return bool(self._max_entries is not None or self._max_bytes is not None)

    def _enforce_limits(self) -> None:
        while self._max_entries is not None and len(self._entries) > self._max_entries:
            removed = self._entries.pop(0)
            self._total_bytes -= len(removed)

        while self._max_bytes is not None and self._total_bytes > self._max_bytes and self._entries:
            removed = self._entries.pop(0)
            self._total_bytes -= len(removed)

    def _rewrite_file(self) -> None:
        if self._path is None:
            return
        with self._path.open("wb") as f:
            for entry in self._entries:
                f.write(struct.pack("!I", len(entry)))
                f.write(entry)
