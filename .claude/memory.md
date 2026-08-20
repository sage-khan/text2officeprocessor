# Durable Decisions

Facts and decisions worth carrying across every future session, settled once
and not worth re-litigating. Not a diary (that's `.claude/sessions.md`); this
is the short list of things a fresh session needs to already know are true.

- **`memory.md`, `sessions.md`, and `tasks.md` all live under `.claude/`, not the repo root (2026-08-19).** This is a public PyPI package; keep the root minimal.
- **This repo is public and open-source (MIT).** Write code, docs, and examples from the perspective of an external contributor who has never seen the codebase — see `.devin/rules/project.md`.
- **`.claude/skills/office-template-cloning/` is the reference implementation `creator-flow` is reusing for its own Slide Generator Agent** (see `creator-flow/docs/plan.md` §3). If this skill's approach changes materially, it's worth telling that project.
- **Documentation convention**: `docs/changelog.md` / `docs/diagnostics.md` (flat, per `.devin/rules/code-review-guidelines.md`), not a `docs/development/` subfolder.
