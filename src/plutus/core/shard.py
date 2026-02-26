"""ShardManager — context sharding for filtering updates to relevant agents."""

from __future__ import annotations

from typing import Any, Callable

from plutus.core.types import Shard


ShardCallback = Callable[[str, Any], None]


class ShardManager:
    """Manages shards and dispatches change events to matching shard callbacks."""

    def __init__(self) -> None:
        self._shards: dict[str, Shard] = {}
        self._callbacks: dict[str, list[ShardCallback]] = {}

    def register(self, shard: Shard, callback: ShardCallback) -> None:
        """Register a shard with a callback for matching changes."""
        self._shards[shard.name] = shard
        self._callbacks.setdefault(shard.name, []).append(callback)

    def unregister(self, shard_name: str) -> None:
        """Remove a shard and its callbacks."""
        self._shards.pop(shard_name, None)
        self._callbacks.pop(shard_name, None)

    def dispatch(self, key: str, value: Any) -> None:
        """Dispatch a change event to all shards whose prefixes match the key."""
        for shard_name, shard in self._shards.items():
            if shard.matches(key):
                for cb in self._callbacks.get(shard_name, []):
                    cb(key, value)

    def get_shard(self, name: str) -> Shard | None:
        return self._shards.get(name)

    @property
    def shard_names(self) -> list[str]:
        return list(self._shards.keys())
