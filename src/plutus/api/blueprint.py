"""Blueprint — declarative state machine with CRDT-backed execution state."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import anyio

from plutus.core.document import PlutusDoc

logger = logging.getLogger(__name__)


@dataclass
class BlueprintNode:
    name: str
    handler: Callable[[BlueprintContext], Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlueprintTransition:
    from_node: str
    to_node: str
    condition: Callable[[BlueprintContext], bool] | None = None


class BlueprintContext:
    """Execution context for blueprint nodes, backed by CRDT state."""

    def __init__(self, doc: PlutusDoc) -> None:
        self._doc = doc
        self._ns = doc.namespace("blueprint")

    @property
    def doc(self) -> PlutusDoc:
        return self._doc

    def get(self, key: str, default: Any = None) -> Any:
        return self._ns.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._ns.set(key, value)

    @property
    def current_node(self) -> str | None:
        return self._ns.get("_current_node")

    @current_node.setter
    def current_node(self, value: str) -> None:
        self._ns.set("_current_node", value)

    @property
    def completed(self) -> bool:
        return self._ns.get("_completed", False)

    @completed.setter
    def completed(self, value: bool) -> None:
        self._ns.set("_completed", value)

    @property
    def history(self) -> list[str]:
        return self._ns.get("_history", [])


class Blueprint:
    """Declarative state machine for multi-step agent workflows.

    Nodes are execution steps; transitions define the flow between them.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._nodes: dict[str, BlueprintNode] = {}
        self._transitions: list[BlueprintTransition] = []
        self._entry_node: str | None = None

    def add_node(
        self,
        name: str,
        handler: Callable[[BlueprintContext], Any],
        **metadata: Any,
    ) -> Blueprint:
        self._nodes[name] = BlueprintNode(name=name, handler=handler, metadata=metadata)
        if self._entry_node is None:
            self._entry_node = name
        return self

    def add_transition(
        self,
        from_node: str,
        to_node: str,
        condition: Callable[[BlueprintContext], bool] | None = None,
    ) -> Blueprint:
        self._transitions.append(
            BlueprintTransition(from_node=from_node, to_node=to_node, condition=condition)
        )
        return self

    def set_entry(self, node_name: str) -> Blueprint:
        self._entry_node = node_name
        return self

    async def execute(self, doc: PlutusDoc | None = None, *, timeout: float | None = None) -> BlueprintContext:
        """Execute the blueprint state machine."""
        import inspect

        doc = doc or PlutusDoc()
        ctx = BlueprintContext(doc)

        if not self._entry_node:
            raise ValueError("No entry node defined")

        ctx.current_node = self._entry_node
        history: list[str] = []

        while ctx.current_node and not ctx.completed:
            node_name = ctx.current_node
            node = self._nodes.get(node_name)
            if not node:
                raise ValueError(f"Node '{node_name}' not found")

            history.append(node_name)
            ctx.set("_history", history)

            async def run_node() -> None:
                result = node.handler(ctx)
                if inspect.isawaitable(result):
                    await result

            try:
                if timeout is None:
                    await run_node()
                else:
                    with anyio.fail_after(timeout):
                        await run_node()
            except TimeoutError as exc:
                logger.warning("blueprint node timed out: %s (timeout=%ss)", node_name, timeout)
                raise TimeoutError(
                    f"Blueprint node '{node_name}' timed out after {timeout}s"
                ) from exc

            doc.commit()

            # Find next transition
            next_node = None
            for trans in self._transitions:
                if trans.from_node == node_name:
                    if trans.condition is None or trans.condition(ctx):
                        next_node = trans.to_node
                        break

            if next_node is None:
                ctx.completed = True
                doc.commit()
            else:
                ctx.current_node = next_node

        return ctx

    @property
    def nodes(self) -> list[str]:
        return list(self._nodes.keys())

    @property
    def transitions(self) -> list[BlueprintTransition]:
        return list(self._transitions)
