# Contributing to Plutus

Thanks for contributing.

## Development Setup (uv)

```bash
uv sync --group dev
```

## Daily Workflow

1. Create a feature branch:
```bash
git checkout -b feat/your-change
```
2. Run tests:
```bash
uv run pytest tests/ -v
```
3. Optional static checks:
```bash
uv run ruff check src tests
uv run mypy src
```
4. Commit with a clear message and open a PR.

## Pull Request Checklist

- Tests updated/added for behavior changes
- `uv run pytest tests/ -v` passes locally
- Public API changes documented in `README.md` and/or docs
- `CHANGELOG.md` updated for notable user-facing changes

## Reporting Bugs

Please use GitHub Issues and include:
- Environment details (`python --version`, OS)
- Reproduction steps
- Expected vs actual behavior
- Minimal code snippet
