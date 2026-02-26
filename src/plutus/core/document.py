"""PlutusDoc + Namespace — typed dict-like access over CRDT state."""

from __future__ import annotations

import logging
from typing import Any, Iterator

from loro import LoroMap

from plutus.core.store import CRDTStore

logger = logging.getLogger(__name__)


class Namespace:
    """Typed dict-like access over a LoroMap within a PlutusDoc."""

    def __init__(self, store: CRDTStore, name: str) -> None:
        self._store = store
        self._name = name
        self._map: LoroMap = store.get_map(name)

    @property
    def name(self) -> str:
        return self._name

    def get(self, key: str, default: Any = None) -> Any:
        result = self._map.get(key)
        if result is None:
            return default
        if hasattr(result, "is_value") and result.is_value:
            return result.value
        return result

    def set(self, key: str, value: Any) -> None:
        if not self._is_supported_value(value):
            raise TypeError(
                f"unsupported value type for CRDT namespace '{self._name}.{key}': {type(value).__name__}"
            )
        normalized = self._normalize_value(value)
        try:
            self._map.insert(key, normalized)
        except Exception as exc:
            logger.exception("failed to write namespace key %s.%s", self._name, key)
            raise TypeError(f"failed to write CRDT value at '{self._name}.{key}'") from exc

    def delete(self, key: str) -> None:
        self._map.delete(key)

    def keys(self) -> list[str]:
        return list(self._map.keys())

    def values(self) -> list[Any]:
        return list(self._map.values())

    def items(self) -> list[tuple[str, Any]]:
        return list(self._map.items())

    def to_dict(self) -> dict[str, Any]:
        return self._map.get_deep_value()

    def __contains__(self, key: str) -> bool:
        return key in self._map

    def __getitem__(self, key: str) -> Any:
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        self.delete(key)

    def __len__(self) -> int:
        return len(self._map)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    @classmethod
    def _is_supported_value(cls, value: Any) -> bool:
        if value is None or isinstance(value, (bool, int, float, str, bytes)):
            return True
        if isinstance(value, (list, tuple)):
            return all(cls._is_supported_value(v) for v in value)
        if isinstance(value, dict):
            return all(isinstance(k, str) and cls._is_supported_value(v) for k, v in value.items())
        return False

    @classmethod
    def _normalize_value(cls, value: Any) -> Any:
        if isinstance(value, tuple):
            return [cls._normalize_value(v) for v in value]
        if isinstance(value, list):
            return [cls._normalize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: cls._normalize_value(v) for k, v in value.items()}
        return value


class PlutusDoc:
    """High-level document wrapping a CRDTStore with namespace access."""

    def __init__(self, store: CRDTStore | None = None, peer_id: int | None = None) -> None:
        self._store = store or CRDTStore(peer_id=peer_id)
        self._namespaces: dict[str, Namespace] = {}

    @property
    def store(self) -> CRDTStore:
        return self._store

    @property
    def peer_id(self) -> int:
        return self._store.peer_id

    def namespace(self, name: str) -> Namespace:
        """Get or create a namespace (backed by a LoroMap)."""
        if name not in self._namespaces:
            self._namespaces[name] = Namespace(self._store, name)
        return self._namespaces[name]

    def state(self, name: str) -> Namespace:
        """Alias for namespace()."""
        return self.namespace(name)

    def commit(self) -> None:
        self._store.commit()

    def export_snapshot(self) -> bytes:
        return self._store.export_snapshot()

    def export_updates(self) -> bytes:
        return self._store.export_updates()

    def import_updates(self, data: bytes) -> None:
        self._store.import_updates(data)

    def get_deep_value(self) -> dict[str, Any]:
        return self._store.get_deep_value()
