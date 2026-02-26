"""Basic swarm example: 3 agents sharing a task list in-process.

Demonstrates CRDT convergence across agents with concurrent writes.
"""

import asyncio
from plutus import PlutusAgent, LifecycleEvent


async def main():
    # Create three agents sharing state via CRDT
    planner = PlutusAgent(name="planner", peer_id=1)
    worker = PlutusAgent(name="worker", peer_id=2)
    reviewer = PlutusAgent(name="reviewer", peer_id=3)

    agents = [planner, worker, reviewer]

    # Join all agents (local mode, no server)
    for agent in agents:
        await agent.join()
        print(f"[{agent.name}] joined (peer_id={agent.peer_id})")

    # Planner creates tasks
    planner.state("tasks").set("task_1", {"desc": "Design API", "status": "pending"})
    planner.state("tasks").set("task_2", {"desc": "Write tests", "status": "pending"})
    planner.state("tasks").set("task_3", {"desc": "Deploy", "status": "pending"})
    planner.commit()
    print(f"\n[planner] Created 3 tasks")

    # Sync planner's state to others via export/import
    updates = planner.doc.export_snapshot()
    worker.doc.import_updates(updates)
    reviewer.doc.import_updates(updates)

    # Worker picks up task_1 and marks it in progress
    worker.state("tasks").set("task_1", {"desc": "Design API", "status": "in_progress", "assignee": "worker"})
    worker.commit()
    print(f"[worker] Picked up task_1")

    # Reviewer concurrently adds a review note
    reviewer.state("reviews").set("task_1", {"note": "Needs API versioning", "reviewer": "reviewer"})
    reviewer.commit()
    print(f"[reviewer] Added review note for task_1")

    # Sync all states — CRDT handles conflict-free merge
    # Worker → Planner and Reviewer
    worker_updates = worker.doc.export_snapshot()
    planner.doc.import_updates(worker_updates)
    reviewer.doc.import_updates(worker_updates)

    # Reviewer → Planner and Worker
    reviewer_updates = reviewer.doc.export_snapshot()
    planner.doc.import_updates(reviewer_updates)
    worker.doc.import_updates(reviewer_updates)

    # All agents now see the merged state
    print(f"\n--- Final State (all agents converged) ---")
    for agent in agents:
        state = agent.doc.get_deep_value()
        print(f"\n[{agent.name}] state:")
        for ns_name, ns_data in state.items():
            print(f"  {ns_name}: {ns_data}")

    # Verify convergence
    states = [a.doc.get_deep_value() for a in agents]
    assert states[0] == states[1] == states[2], "States diverged!"
    print(f"\nAll 3 agents converged to identical state!")

    # Worker completes task_1
    worker.state("tasks").set("task_1", {"desc": "Design API", "status": "done", "assignee": "worker"})
    worker.commit()

    # Sync final update
    final = worker.doc.export_snapshot()
    planner.doc.import_updates(final)
    reviewer.doc.import_updates(final)

    print(f"\n[worker] Completed task_1")
    print(f"[planner] sees task_1 status: {planner.state('tasks').get('task_1')}")

    # Leave
    for agent in agents:
        await agent.leave()
        print(f"[{agent.name}] left")


if __name__ == "__main__":
    asyncio.run(main())
