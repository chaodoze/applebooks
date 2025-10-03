# Repository Guidelines

## Project Structure & Module Organization
The Python package lives in `abx/`, with modules split by responsibility: `cli.py` orchestrates the CLI entrypoint, `epub_parser.py` handles ingest, `cleaner.py` normalizes HTML, `llm.py` coordinates OpenAI/BAML calls, and `persistence.py` talks to SQLite. Companion geospatial tools ship under `abxgeo/`. Generated BAML clients land in `baml_client/`; regenerate instead of editing by hand. Schemas for extraction output live in `schema/`, while reference SQLite fixtures and run logs sit at the repo root. Tests reside in `tests/` and mirror the package structure.

## Build, Test, and Development Commands
- `pip install -e ".[dev]"` installs the package with tooling used in CI checks.
- `baml-cli generate` refreshes the client after schema updates; run from the repo root.
- `abx extract --epub <path> --db test_library.sqlite --schema schema/story.schema.json --batch` executes a full extraction against local fixtures.
- `ruff check .` and `ruff format .` enforce linting and formatting expectations.
- `pytest` runs the test suite; append `-k resolver` to focus on the resolver coverage during iteration.

## Coding Style & Naming Conventions
Use 4-space indentation, keep modules Pythonic, and prefer descriptive, lowercase module names (`persistence.py`). Public functions and CLI commands should read in imperative voice (`extract_chapters`, `abx extract`). Type hints are required on new interfaces touching LLM payloads. Allow long strings for prompts, but wrap other code at roughly 120 characters to align with the Ruff `line-length`. Document non-obvious flows with short comments above the block.

## Testing Guidelines
Pytest drives coverage; place new tests in `tests/` with filenames matching the target module (e.g., `test_llm.py`). Parametrize edge cases such as retry behaviour or alternate cleaning modes. Use the SQLite fixtures under the repo root when integration coverage is needed, but reset temporary databases between assertions. Run `pytest --maxfail=1` before pushing, and include `pytest -q tests/test_resolver.py::test_status_matrix` when reproducing resolver regressions.

## Commit & Pull Request Guidelines
Follow the existing sentence-case, action-oriented commit style ("Refine story extraction prompt..."); group logically related changes per commit. PRs should summarize intent, list the commands you ran (`pytest`, `ruff`), and link associated issues or notebooks. Attach screenshots or log excerpts when visual diffs or CLI output prove a fix. Request review whenever LLM prompt text or schema contracts change, noting any downstream BAML regeneration requirements.

## Configuration & Secrets
Set `OPENAI_API_KEY` in your shell before running the CLI, and avoid committing `.env` files. When experimenting with new BAML schemas, bump the schema version and regenerate clients so batch jobs remain deterministic. Keep SQLite artifacts with sensitive data out of the repo; use the existing test databases or create throwaway copies under `tmp/`.
