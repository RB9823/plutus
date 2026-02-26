# Releasing Plutus (uv-first)

This project uses `uv` for build/test/publish.

## One-Time Setup

1. Create package projects:
   - PyPI: `plutus`
   - TestPyPI: `plutus` (recommended for rehearsal)
2. Configure Trusted Publishing in both indexes.
3. Ensure GitHub Actions publish jobs have `id-token: write` (already set in workflow).

### Trusted Publishing values

In PyPI/TestPyPI project settings, add a Pending Publisher with:

- Owner: `<your-github-owner>`
- Repository: `<your-repo>`
- Workflow name: `publish.yml`
- Environment:
  - `pypi` for production publishing
  - `testpypi` for rehearsal publishing

The publish workflow is at `.github/workflows/publish.yml`.

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
   - Tag must match package version (e.g. tag `v0.1.1` with `version = "0.1.1"`).

## TestPyPI Dry Run (recommended)

Run workflow manually from GitHub Actions:
- Workflow: `Publish`
- Input `repository`: `testpypi`

Then install from TestPyPI:

```bash
uv pip install --index-url https://test.pypi.org/simple/ plutus
```

## Manual Publish (fallback)

If needed:
```bash
uv publish
```

This requires local PyPI credentials/token configuration.
