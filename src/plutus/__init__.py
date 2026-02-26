"""Plutus — CRDT-based state management for agentic swarms."""

from plutus._version import __version__
from plutus.api.agent import PlutusAgent
from plutus.api.blueprint import Blueprint, BlueprintContext
from plutus.api.lifecycle import LifecycleEvent
from plutus.core.decorators import shared, synced
from plutus.core.document import PlutusDoc
from plutus.core.types import Shard

__all__ = [
    "__version__",
    "Blueprint",
    "BlueprintContext",
    "LifecycleEvent",
    "PlutusAgent",
    "PlutusDoc",
    "Shard",
    "shared",
    "synced",
]
