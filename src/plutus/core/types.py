"""Type definitions for the Plutus core module."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


PeerID = int
ShardKey = str
Callback = Callable[..., Any]


class ContainerKind(Enum):
    MAP = auto()
    LIST = auto()
    TEXT = auto()
    COUNTER = auto()


@dataclass
class Shard:
    """Defines a named slice of the CRDT document that an agent cares about."""

    name: str
    prefixes: list[str] = field(default_factory=list)

    def matches(self, key: str) -> bool:
        if not self.prefixes:
            return True
        return any(key.startswith(p) for p in self.prefixes)
