# Contributing to MD2Office

Thank you for your interest in contributing. This document explains how to set up your environment and the standards expected.

---

## Getting Started

```bash
git clone https://github.com/sage-khan/md2office
cd md2office
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov ruff
```

Run tests before making any changes:

```bash
python -m pytest tests/ -v
```

All 38 tests must pass before you begin.

---

## Branching

```
feature/<your-feature> → dev → main
```

- Work on `dev` or a `feature/*` branch
- Submit pull requests to `dev`
- `main` is for production-ready releases only

---

## Commit Message Format

Follow conventional commits:

```
feat: add Groq LLM provider support
fix: handle missing List Bullet style in custom DOCX templates
docs: update architecture diagram with XLSX flow
test: add edge case for multiline placeholder parsing
refactor: extract _normalize() into shared utils
```

---

## Non-Negotiable Architecture Rules

Any PR that violates these will be rejected:

1. **PPTX must use `SlidePart` cloning** — never `add_slide()` alone, never `deepcopy(slide)`
2. **DOCX must iterate `element.body` children in order** — tables must stay inline
3. **LLM scope is strictly normalization** — LLM cannot generate final document content
4. **No layout mutation** — never move, resize, or rebuild shapes
5. **No markdown artifacts** — all `**`, `__`, `---` must be stripped before saving

See `.windsurf/rules/md2office-rules.md` for the full technical specification.

---

## Adding a New LLM Provider

1. Create a class in `src/core/llm/providers.py` extending `LLMProvider`
2. Implement `generate(self, prompt: str) -> str`
3. Register it in the `build_provider()` factory
4. Add tests in a new `tests/test_llm_<provider>.py`
5. Update `config/llm_config.yaml` with default config

---

## Adding a New Output Engine

1. Create `src/core/engines/<format>/engine.py`
2. Implement `render(plan, output_path) -> Path`
3. Add the format to `OutputFormat` enum in `src/core/models.py`
4. Wire it in `src/cli/main.py`
5. Write tests

---

## Code Style

- Python 3.10+
- Type hints on all public functions
- Dataclasses for domain models
- `logging` for library code, `print` only in CLI
- All file I/O via `pathlib.Path`
- Line length: 120 characters
- Run `ruff check src/ tests/` before submitting

---

## Documentation

- Update `docs/development/changelog.md` with your changes (timestamped entry)
- Update `docs/development/diagnostics.md` for any bug fixes
- Do not create separate status/tracking documents

---

## Test Requirements

- All existing tests must pass
- New features require new tests
- Target: one test per public function for core modules
- Integration tests should use the provided sample fixtures in `tests/data/` and `tests/templates/`
