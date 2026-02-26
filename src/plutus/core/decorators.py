"""@synced descriptor and @shared class decorator for declarative CRDT-backed state."""

from __future__ import annotations

from typing import Any


class synced:
    """Descriptor that maps an attribute to a key in the agent's CRDT namespace.

    Usage:
        class MyAgent(PlutusAgent):
            task_count = synced(default=0)
            name = synced(default="")
    """

    def __init__(self, *, default: Any = None, ns: str = "state", auto_commit: bool = False) -> None:
        self.default = default
        self.ns = ns
        self.auto_commit = auto_commit
        self.attr_name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        doc = obj._plutus_doc
        ns = doc.namespace(self.ns)
        val = ns.get(self.attr_name)
        return val if val is not None else self.default

    def __set__(self, obj: Any, value: Any) -> None:
        doc = obj._plutus_doc
        ns = doc.namespace(self.ns)
        ns.set(self.attr_name, value)
        if self.auto_commit:
            commit = getattr(obj, "commit", None)
            if callable(commit):
                commit()
            else:
                doc.commit()


def shared(cls: type | None = None, *, ns: str = "state") -> Any:
    """Class decorator that auto-registers synced descriptors with a namespace.

    Usage:
        @shared
        class MyAgent(PlutusAgent):
            task_count = synced(default=0)
    """
    def wrap(cls: type) -> type:
        for attr_name in list(vars(cls)):
            attr = getattr(cls, attr_name)
            if isinstance(attr, synced):
                attr.ns = ns
        cls._plutus_shared_ns = ns
        return cls

    if cls is not None:
        return wrap(cls)
    return wrap
