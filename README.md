# Plutus

CRDT-based state management for agentic swarms.

Plutus provides:
- `PlutusAgent` for local/networked swarm participation
- CRDT-backed shared namespaces and descriptors
- A sync daemon + WebSocket transport
- Blueprint workflow execution for multi-step agent flows

## Quick Start (uv)

### 1. Install as a dependency

```bash
uv add plutus-sync
```

### 2. Run locally from source

```bash
git clone https://github.com/RB9823/plutus.git
cd plutus
uv sync --group dev
uv run pytest tests/ -v
```

### 3. Try examples

```bash
uv run python examples/basic_swarm.py
uv run python examples/networked_swarm.py
uv run python examples/blueprint_example.py
```

## Minimal Usage

Install name is `plutus-sync`; import package remains `plutus`.

```python
import anyio
from plutus import PlutusAgent


async def main():
    agent = PlutusAgent(name="worker", peer_id=1)
    await agent.join()
    agent.state("tasks").set("task_1", {"status": "pending"})
    agent.commit()
    await agent.leave()


anyio.run(main)
```

## Development

- Setup: `uv sync --group dev`
- Tests: `uv run pytest tests/ -v`
- Linting: `uv run ruff check src tests`
- Type checking: `uv run mypy src`

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contributor workflow.

## Releasing

See [docs/RELEASING.md](docs/RELEASING.md) for the uv-based release process and PyPI publishing setup.
Use workflow-dispatch to publish to `testpypi` first, then publish to `pypi` from a GitHub Release.

## Project Health

- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- License: [LICENSE](LICENSE)
