"""Networked swarm example: 2 agents syncing over WebSocket via SyncDaemon.

Run this script to see two agents exchange state through a central hub.
"""

import anyio
from plutus import PlutusAgent
from plutus.infra.daemon import SyncDaemon


async def run_agent(
    name: str,
    peer_id: int,
    port: int,
    write_data: dict,
    expected_keys: set[str],
    delay: float = 0.5,
    settle_before_write: float = 0.5,
):
    """Connect an agent to the daemon and observe auto-sync convergence."""
    await anyio.sleep(delay)  # stagger connections

    agent = PlutusAgent(name=name, peer_id=peer_id)
    await agent.join(server_uri=f"ws://localhost:{port}")
    print(f"[{name}] connected to daemon")
    await anyio.sleep(settle_before_write)

    # Write data
    for key, value in write_data.items():
        agent.state("shared").set(key, value)
    await agent.sync()
    print(f"[{name}] wrote {len(write_data)} entries")

    # Wait for remote updates to arrive automatically.
    with anyio.fail_after(5):
        while True:
            shared = agent.state("shared").to_dict()
            if expected_keys.issubset(shared.keys()):
                break
            await anyio.sleep(0.05)
    print(f"[{name}] observed remote updates automatically")

    state = agent.doc.get_deep_value()
    print(f"[{name}] final state: {state}")

    await agent.leave()
    return state


async def main():
    port = 8766

    # Start SyncDaemon
    daemon = SyncDaemon(port=port)
    await daemon.start()
    print(f"SyncDaemon running on ws://localhost:{port}")

    try:
        async with anyio.create_task_group() as tg:
            # Agent A writes tasks
            async def agent_a():
                state = await run_agent(
                    "agent_a", peer_id=100, port=port,
                    write_data={"task_1": "Design system", "task_2": "Build MVP"},
                    expected_keys={"task_1", "task_2", "config_1", "config_2"},
                    delay=0.2,
                )
                return state

            # Agent B writes config
            async def agent_b():
                state = await run_agent(
                    "agent_b", peer_id=200, port=port,
                    write_data={"config_1": "Production", "config_2": "v2.0"},
                    expected_keys={"task_1", "task_2", "config_1", "config_2"},
                    delay=0.4,
                )
                return state

            tg.start_soon(agent_a)
            tg.start_soon(agent_b)

    finally:
        # Check daemon state
        daemon_state = daemon.store.get_deep_value()
        print(f"\n[daemon] aggregated state: {daemon_state}")
        print(f"[daemon] peers seen: {daemon.peers.peer_ids}")
        print(f"[daemon] log entries: {len(daemon.event_log)}")
        await daemon.stop()
        print("SyncDaemon stopped")


if __name__ == "__main__":
    anyio.run(main)
