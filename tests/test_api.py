"""Tests for API module: lifecycle, agent, blueprint."""

import anyio
import pytest

from plutus.api.lifecycle import LifecycleEvent, LifecycleManager
from plutus.api.agent import PlutusAgent
from plutus.api.blueprint import Blueprint, BlueprintContext
from plutus.core.document import PlutusDoc


class TestLifecycleManager:
    def test_hook_firing(self):
        mgr = LifecycleManager()
        events = []
        mgr.on(LifecycleEvent.AFTER_JOIN, lambda *a: events.append("join"))
        mgr.on(LifecycleEvent.AFTER_LEAVE, lambda *a: events.append("leave"))

        mgr.fire(LifecycleEvent.AFTER_JOIN)
        mgr.fire(LifecycleEvent.AFTER_LEAVE)

        assert events == ["join", "leave"]

    def test_multiple_hooks(self):
        mgr = LifecycleManager()
        calls = []
        mgr.on(LifecycleEvent.ON_STATE_CHANGE, lambda: calls.append(1))
        mgr.on(LifecycleEvent.ON_STATE_CHANGE, lambda: calls.append(2))
        mgr.fire(LifecycleEvent.ON_STATE_CHANGE)
        assert calls == [1, 2]

    def test_decorator_hook(self):
        mgr = LifecycleManager()
        calls = []

        @mgr.hook(LifecycleEvent.AFTER_JOIN)
        def on_join(*args):
            calls.append("joined")

        mgr.fire(LifecycleEvent.AFTER_JOIN)
        assert calls == ["joined"]

    def test_off(self):
        mgr = LifecycleManager()
        calls = []
        fn = lambda: calls.append(1)
        mgr.on(LifecycleEvent.AFTER_JOIN, fn)
        mgr.off(LifecycleEvent.AFTER_JOIN, fn)
        mgr.fire(LifecycleEvent.AFTER_JOIN)
        assert calls == []


class TestPlutusAgent:
    @pytest.mark.anyio
    async def test_join_leave_cycle(self):
        agent = PlutusAgent(name="worker", peer_id=42)
        events = []
        agent.on(LifecycleEvent.AFTER_JOIN, lambda a: events.append("join"))
        agent.on(LifecycleEvent.AFTER_LEAVE, lambda a: events.append("leave"))

        # Local join (no server)
        await agent.join()
        assert agent.is_joined

        agent.state("tasks").set("t1", "plan")
        agent.commit()
        assert agent.state("tasks").get("t1") == "plan"

        await agent.leave()
        assert not agent.is_joined
        assert events == ["join", "leave"]

    @pytest.mark.anyio
    async def test_agent_state(self):
        agent = PlutusAgent(name="planner")
        await agent.join()

        agent.state("tasks").set("task_1", {"status": "pending", "desc": "Plan project"})
        agent.commit()

        deep = agent.doc.get_deep_value()
        assert "tasks" in deep

        await agent.leave()

    @pytest.mark.anyio
    async def test_complete(self):
        agent = PlutusAgent(name="agent")
        await agent.join()
        assert agent.is_joined
        await agent.complete()
        assert not agent.is_joined

    @pytest.mark.anyio
    async def test_async_lifecycle_hooks_are_awaited(self):
        agent = PlutusAgent(name="worker", peer_id=11)
        events = []

        async def before_join(_agent):
            await anyio.sleep(0)
            events.append("before_join")

        async def after_leave(_agent):
            await anyio.sleep(0)
            events.append("after_leave")

        agent.on(LifecycleEvent.BEFORE_JOIN, before_join)
        agent.on(LifecycleEvent.AFTER_LEAVE, after_leave)

        await agent.join()
        await agent.leave()
        assert events == ["before_join", "after_leave"]


class TestBlueprint:
    @pytest.mark.anyio
    async def test_three_node_state_machine(self):
        results = []

        def plan(ctx: BlueprintContext):
            ctx.set("plan", "Build feature X")
            results.append("plan")

        def execute(ctx: BlueprintContext):
            plan = ctx.get("plan")
            ctx.set("result", f"Executed: {plan}")
            results.append("execute")

        def review(ctx: BlueprintContext):
            result = ctx.get("result")
            ctx.set("review", f"Reviewed: {result}")
            results.append("review")

        bp = Blueprint("workflow")
        bp.add_node("plan", plan)
        bp.add_node("execute", execute)
        bp.add_node("review", review)
        bp.add_transition("plan", "execute")
        bp.add_transition("execute", "review")

        ctx = await bp.execute()

        assert results == ["plan", "execute", "review"]
        assert ctx.completed
        assert ctx.get("plan") == "Build feature X"
        assert ctx.get("result") == "Executed: Build feature X"
        assert ctx.get("review") == "Reviewed: Executed: Build feature X"

    @pytest.mark.anyio
    async def test_conditional_transition(self):
        def step_a(ctx: BlueprintContext):
            ctx.set("score", 80)

        def step_pass(ctx: BlueprintContext):
            ctx.set("outcome", "pass")

        def step_fail(ctx: BlueprintContext):
            ctx.set("outcome", "fail")

        bp = Blueprint("conditional")
        bp.add_node("check", step_a)
        bp.add_node("pass", step_pass)
        bp.add_node("fail", step_fail)
        bp.add_transition("check", "pass", condition=lambda ctx: ctx.get("score", 0) >= 70)
        bp.add_transition("check", "fail", condition=lambda ctx: ctx.get("score", 0) < 70)

        ctx = await bp.execute()
        assert ctx.get("outcome") == "pass"

    @pytest.mark.anyio
    async def test_blueprint_with_shared_doc(self):
        doc = PlutusDoc()

        def writer(ctx: BlueprintContext):
            ctx.set("data", "shared_value")

        bp = Blueprint("shared")
        bp.add_node("write", writer)
        ctx = await bp.execute(doc=doc)

        assert doc.namespace("blueprint").get("data") == "shared_value"

    def test_blueprint_nodes_and_transitions(self):
        bp = Blueprint("test")
        bp.add_node("a", lambda ctx: None)
        bp.add_node("b", lambda ctx: None)
        bp.add_transition("a", "b")
        assert bp.nodes == ["a", "b"]
        assert len(bp.transitions) == 1

    @pytest.mark.anyio
    async def test_blueprint_async_handler(self):
        async def step(ctx: BlueprintContext):
            await anyio.sleep(0)
            ctx.set("done", True)

        bp = Blueprint("async")
        bp.add_node("step", step)
        ctx = await bp.execute()
        assert ctx.get("done") is True

    @pytest.mark.anyio
    async def test_blueprint_timeout(self):
        async def slow_step(ctx: BlueprintContext):
            await anyio.sleep(0.2)
            ctx.set("done", True)

        bp = Blueprint("timeout")
        bp.add_node("slow", slow_step)

        with pytest.raises(TimeoutError):
            await bp.execute(timeout=0.01)
