"""LifecycleManager + LifecycleEvent enum for agent lifecycle hooks."""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Callable


class LifecycleEvent(Enum):
    BEFORE_JOIN = auto()
    AFTER_JOIN = auto()
    BEFORE_LEAVE = auto()
    AFTER_LEAVE = auto()
    ON_STATE_CHANGE = auto()
    ON_PEER_JOIN = auto()
    ON_PEER_LEAVE = auto()
    ON_ERROR = auto()


LifecycleHook = Callable[..., Any]


class LifecycleManager:
    """Manages registration and firing of agent lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: dict[LifecycleEvent, list[LifecycleHook]] = {}

    def on(self, event: LifecycleEvent, hook: LifecycleHook) -> None:
        self._hooks.setdefault(event, []).append(hook)

    def off(self, event: LifecycleEvent, hook: LifecycleHook) -> None:
        hooks = self._hooks.get(event, [])
        if hook in hooks:
            hooks.remove(hook)

    def fire(self, event: LifecycleEvent, *args: Any, **kwargs: Any) -> None:
        for hook in self._hooks.get(event, []):
            hook(*args, **kwargs)

    async def fire_async(self, event: LifecycleEvent, *args: Any, **kwargs: Any) -> None:
        import inspect
        for hook in self._hooks.get(event, []):
            result = hook(*args, **kwargs)
            if inspect.isawaitable(result):
                await result

    def hook(self, event: LifecycleEvent) -> Callable[[LifecycleHook], LifecycleHook]:
        """Decorator to register a lifecycle hook."""
        def decorator(fn: LifecycleHook) -> LifecycleHook:
            self.on(event, fn)
            return fn
        return decorator
