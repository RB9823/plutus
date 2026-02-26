"""Blueprint example: 3-node workflow with CRDT-persisted execution state.

Demonstrates a plan → execute → review pipeline using Blueprint.
"""

import asyncio
from plutus import Blueprint, BlueprintContext, PlutusDoc


def plan_phase(ctx: BlueprintContext):
    """Planning phase: define the work to be done."""
    ctx.set("plan", {
        "objective": "Build user authentication",
        "tasks": ["Design schema", "Implement endpoints", "Write tests"],
        "estimated_hours": 8,
    })
    ctx.set("phase", "planning")
    print("[plan] Created project plan")
    print(f"  Objective: {ctx.get('plan')['objective']}")
    print(f"  Tasks: {ctx.get('plan')['tasks']}")


def execute_phase(ctx: BlueprintContext):
    """Execution phase: carry out the plan."""
    plan = ctx.get("plan")
    completed = []
    for task in plan["tasks"]:
        completed.append({"task": task, "status": "done"})
        print(f"  [execute] Completed: {task}")

    ctx.set("results", completed)
    ctx.set("phase", "execution")
    ctx.set("hours_spent", 7)
    print(f"[execute] All {len(completed)} tasks completed in {ctx.get('hours_spent')}h")


def review_phase(ctx: BlueprintContext):
    """Review phase: evaluate the results."""
    results = ctx.get("results")
    hours = ctx.get("hours_spent")
    plan = ctx.get("plan")

    all_done = all(r["status"] == "done" for r in results)
    under_budget = hours <= plan["estimated_hours"]

    review = {
        "all_tasks_completed": all_done,
        "under_budget": under_budget,
        "verdict": "approved" if (all_done and under_budget) else "needs_revision",
    }
    ctx.set("review", review)
    ctx.set("phase", "review")
    print(f"[review] Verdict: {review['verdict']}")
    print(f"  All tasks done: {all_done}")
    print(f"  Under budget: {under_budget} ({hours}h / {plan['estimated_hours']}h)")


async def main():
    # Build the blueprint
    bp = Blueprint("project_workflow")
    bp.add_node("plan", plan_phase)
    bp.add_node("execute", execute_phase)
    bp.add_node("review", review_phase)
    bp.add_transition("plan", "execute")
    bp.add_transition("execute", "review")

    print("=== Blueprint Workflow ===")
    print(f"Nodes: {bp.nodes}")
    print(f"Transitions: {len(bp.transitions)}\n")

    # Execute with a shared CRDT document
    doc = PlutusDoc()
    ctx = await bp.execute(doc=doc)

    # Inspect final CRDT state
    print(f"\n=== Final CRDT State ===")
    state = doc.get_deep_value()
    bp_state = state.get("blueprint", {})
    print(f"Current node: {bp_state.get('_current_node')}")
    print(f"Completed: {bp_state.get('_completed')}")
    print(f"Phase: {bp_state.get('phase')}")
    print(f"Review verdict: {bp_state.get('review', {}).get('verdict')}")
    print(f"History: {bp_state.get('_history')}")

    # The CRDT state can be exported and shared with other agents
    snapshot = doc.export_snapshot()
    print(f"\nSnapshot size: {len(snapshot)} bytes")
    print("Blueprint execution complete!")


if __name__ == "__main__":
    asyncio.run(main())
