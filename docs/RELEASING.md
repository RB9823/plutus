# Releasing Plutus (uv-first)

This project uses `uv` for build/test/publish.

## One-Time Setup

1. Create a PyPI project named `plutus`.
2. Configure PyPI Trusted Publishing for this repository (`pypa/gh-action-pypi-publish`).
3. Ensure GitHub Actions has `id-token: write` permission for publish workflow.

## Release Checklist

1. Update version in:
   - `pyproject.toml` (`[project].version`)
   - `src/plutus/_version.py` (`__version__`)
2. Update `CHANGELOG.md`.
3. Run required validation:
```bash
uv sync --group dev
uv run pytest tests/ -v
```
4. Optional quality checks before release:
```bash
uv run ruff check src tests
uv run mypy src
```
5. Build distributions:
```bash
uv build
```
6. Optional local inspection:
```bash
ls -lh dist/
```
7. Create a Git tag and GitHub Release:
```bash
git tag v0.1.1
git push origin v0.1.1
```
8. Publish is handled by `.github/workflows/publish.yml` on Release publish.

## Manual Publish (fallback)

If needed:
```bash
uv publish
```

This requires local PyPI credentials/token configuration.
