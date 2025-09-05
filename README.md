# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: FastAPI app exposing `/health`, `/chat`, and `/ingest`.
- `store.py`: Chroma persistence (`chroma_store/`) and a small SQLite session store.
- `embedder.py`: Sentence-transformers embedding helper.
- `crawler.py`: Domain-restricted crawler (requests + trafilatura).
- `ingest.py`: CLI to ingest pages, orders, and conversation logs.
- `prompts.py`: System prompt and refusal text.
- `test_api.py`: Lightweight smoke test using FastAPI `TestClient`.
- Assets: `widget.html`, `widget.js`, `test_widget.html`. Local state: `chroma_store/`.

## Build, Test, and Development Commands
- Setup (Python 3.11): `python -m venv venv && .\\venv\\Scripts\\activate` (Windows) or `source venv/bin/activate` (Unix)
- Install deps: `pip install -r requirements.txt`
- Run API (dev): `uvicorn app:app --reload`
- Health check: `curl http://localhost:8000/health`
- Chat example:
  `curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"session_id":"dev","message":"Hello","k":4}'`
- Ingest site: `python ingest.py --site https://example.com --max_pages 40`
- Smoke test: `python test_api.py` (prints status/output; pytest not required here).

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and type hints.
- Modules/files: `snake_case.py`; functions/vars: `snake_case`; classes: `CamelCase`.
- Keep endpoints small and pure; prefer f-strings and clear docstrings.
- No enforced formatter/linter in repo; keep code black-like and import order sane.

## Testing Guidelines
- Add tests as `test_*.py` at repo root (align with `test_api.py`).
- Use FastAPI `TestClient` for endpoint tests; prefer lightweight, deterministic cases.
- If adding broader tests, you may introduce `pytest` (optional) and keep them fast; no coverage gate is enforced.

## Commit & Pull Request Guidelines
- Use Conventional Commits (e.g., `feat:`, `fix:`, `docs:`) with concise scope and motivation.
- PRs: include a clear description, reproduction/validation steps (commands), and note any env vars or data impacts.
- Link related issues; keep changes focused and reasonably small.

## Security & Configuration Tips
- Copy `.env.example` to `.env` as needed. Useful vars: `MODEL_ID`, `EMBED_MODEL`, `PERSIST_DIR`, `TENANT_ID`, `ALLOWED_DOMAIN`.
- CORS is permissive for dev; restrict origins before production.
- Treat `chroma_store/` and `venv/` as local state; avoid committing large artifacts.
